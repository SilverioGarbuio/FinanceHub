from optparse import OptionParser
import datetime as dt
import pandas as pd
import blpapi
import numpy as np


class BBG(object):

    def __init__(self):
        self.options = BBG._parse_cmd_line()

    def fetch_series(self, securities, fields, startdate, enddate, period="DAILY", calendar="ACTUAL", fx=None,
                     fperiod=None, verbose=False):

        startdate = BBG._assert_date_type(startdate)
        enddate = BBG._assert_date_type(enddate)

        bbg_start_date = BBG._datetime_to_bbg_string(startdate)
        bbg_end_date = BBG._datetime_to_bbg_string(enddate)

        if startdate > enddate:
            ValueError("Start date is later than end date")

        session_options = blpapi.SessionOptions()
        session_options.setServerHost(self.options.host)
        session_options.setServerPort(self.options.port)
        session = blpapi.Session(session_options)

        if not session.start():
            raise ConnectionError("Failed to start session")

        try:
            if not session.openService("//blp/refdata"):
                raise ConnectionError("Failed to open //blp/refdat")

            # Obtain the previously opened service
            refdata_service = session.getService("//blp/refdata")

            # Create and fill the request for historical data
            request = refdata_service.createRequest("HistoricalDataRequest")

            # grab securities
            if type(securities) is list:
                for sec in securities:
                    request.getElement("securities").appendValue(sec)
            else:
                request.getElement("securities").appendValue(securities)

            # grab fields
            if type(fields) is list:
                for f in fields:
                    request.getElement("fields").appendValue(f)
            else:
                request.getElement("fields").appendValue(fields)

            request.set("periodicityAdjustment", calendar)
            request.set("periodicitySelection", period)
            request.set("startDate", bbg_start_date)
            request.set("endDate", bbg_end_date)
            request.set("maxDataPoints", 30000)

            if not (fx is None):
                request.set("currency", fx)

            if not (fperiod is None):
                overrides_bdh = request.getElement("overrides")
                override1_bdh = overrides_bdh.appendElement()
                override1_bdh.setElement("fieldId", "BEST_FPERIOD_OVERRIDE")
                override1_bdh.setElement("value", fperiod)

            if verbose:
                print("Sending Request:", request.getElement("date").getValue())

            # send request
            session.sendRequest(request)

            # process received response
            results = {}

            while True:
                ev = session.nextEvent(500)

                for msg in ev:

                    if verbose:
                        print(msg)

                    if msg.messageType().__str__() == "HistoricalDataResponse":
                        sec_data = msg.getElement("securityData")
                        sec_name = sec_data.getElement("security").getValue()
                        field_data = sec_data.getElement("fieldData")

                        if type(fields) is list:

                            results[sec_name] = {}

                            for day in range(field_data.numValues()):

                                fld = field_data.getValue(day)

                                for fld_i in fields:
                                    if fld.hasElement(fld_i):
                                        results[sec_name]\
                                            .setdefault(fld_i, []).append([fld.getElement("date").getValue(),
                                                                           fld.getElement(fld_i).getValue()])
                        else:
                            results[sec_name] = []
                            for day_i in range(field_data.numValues()):
                                fld = field_data.getValue(day_i)
                                results[sec_name].append([
                                    fld.getElement("date").getValue(),
                                    fld.getElement(fields).getValue()])

                if ev.eventType() == blpapi.Event.RESPONSE:  # Response completly received, break out of the loop
                    break

        finally:
            session.stop()

        if not type(securities) is list:
            results = results[securities]

        # parse the results as a DataFrame
        df = pd.DataFrame()

        if not (type(securities) is list) and not (type(fields) is list):
            # single ticker and single field
            # returns a dataframe with a single column
            results = np.array(results)
            df[securities] = pd.Series(index=results[:, 0], data=results[:, 1])

        elif (type(securities) is list) and not (type(fields) is list):
            # multiple tickers and single field
            # returns a single dataframe for the field with the ticker on the columns

            for tick in results.keys():
                aux = np.array(results[tick])
                df[tick] = pd.Series(index=aux[:, 0], data=aux[:, 1])

        elif not (type(securities) is list) and (type(fields) is list):
            # single ticker and multiple fields
            # returns a single dataframe for the ticker with the fields on the columns

            for fld in results.keys():
                aux = np.array(results[fld])
                df[fld] = pd.Series(index=aux[:, 0], data=aux[:, 1])

        else:
            # multiple tickers and multiple fields
            # returns a multi-index dataframe with [field, ticker] as index

            for tick in results.keys():

                for fld in results[tick].keys():
                    aux = np.array(results[tick][fld])
                    df_aux = pd.DataFrame(data={'FIELD': fld,
                                                'TRADE_DATE': aux[:, 0],
                                                'TICKER': tick,
                                                'VALUE': aux[:, 1]})
                    df = df.append(df_aux)

            df['VALUE'] = df['VALUE'].astype(float)
            df['TRADE_DATE'] = df['TRADE_DATE'].astype(pd.Timestamp)

            df = pd.pivot_table(data=df, index=['FIELD', 'TRADE_DATE'], columns='TICKER', values='VALUE')

        return df

    @staticmethod
    def _parse_cmd_line():

        parser = OptionParser(description="Retrive reference data.")

        parser.add_option("-a", "--ip", dest="host", help="server name or IP (default: %default)",
                          metavar="ipAdress", default="localhost")

        parser.add_option("-p", dest="port", type="int", help="server port (default: %default)",
                          metavar="tcpPort", default=8194)

        (options, args) = parser.parse_args()

        return options

    @staticmethod
    def _assert_date_type(input_date):
        """

        :param input_date: str, timestamp, datetime
        :return: input_date in datetime format
        """

        if not (type(input_date) is dt.date):

            if type(input_date) is pd.Timestamp:
                input_date = input_date.date()

            elif type(input_date) is str:
                input_date = pd.to_datetime(input_date).date()

            else:
                raise TypeError("Date format not supported")

        return input_date

    @staticmethod
    def _datetime_to_bbg_string(input_date):
        return str(input_date.year)+str(input_date.month).zfill(2)+str(input_date.day).zfill(2)


"""
* test for different types of dates
* write documentation
    - no more than 30k point per request
* write README
* assert variable types
"""