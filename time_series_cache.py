'''
Created on Jul 29, 2013

@author: akittredge
'''
import itertools


class FinancialDataTimeSeriesCache(object):
    def __init__(self, gets_data, database):
        self._get_data = gets_data
        self._database = database
        
    def get(self, symbol, dates):
        '''yield date, data pairs in no particular order.
        dates is a list of UTC datetimes.
        
        '''
        cached_values = list(self._database.get(symbol=symbol, dates=dates))
        missing_dates = set(dates)
        for date, value in cached_values:
            missing_dates.remove(date)
            yield date, value
        if missing_dates:
            for date, value in self._get_set(symbol, dates=missing_dates):
                yield date, value

    def _get_set(self, symbol, dates):
        new_records = list(self._get_data(symbol, dates))
        self._database.set(symbol, new_records)
        return new_records

class FinancialDataRangesCache(object):
    def __init__(self, gets_data, database):
        self._get_data = gets_data
        self._database = database
        
    def get(self, symbols, dates):
        for symbol in symbols:
            for date in dates:
                # Not looking for more than one date at a time because the set
                # operation will set multiple dates per call.
                cached_value = self._database.get(symbol=symbol, date=date)
                if not cached_value:
                    self._get_set(symbol=symbol, date=date)
                    # Value will be in the database now.
                    # Superfluous database call.
                    yield self._database.get(symbol=symbol, date=date)
                else:
                    yield cached_value

    def _get_set(self, symbol, date):
        start, value, end = self._get_data(symbol=symbol, date=date)
        self._database.set_interval(symbol=symbol, start=start, end=end, value=value)

import unittest
import mock
import datetime
class FinancialDataRangesCacheTestCase(unittest.TestCase):
    def setUp(self):
        self.mock_data_getter = mock.Mock()
        self.mock_db = mock.Mock()
        self.date_range_cache = FinancialDataRangesCache(gets_data=self.mock_data_getter,
                                                         database=self.mock_db)
        
    def test_get_cache_hit(self):
        symbol = 'ABC'
        date = datetime.datetime(2012, 12, 1)
        value = 100.
        self.mock_db.get.return_value = {'date' : date,
                                         'symbol' : symbol,
                                         'EPS' : value}
        cache_value = self.date_range_cache.get(symbols=[symbol], dates=[date]).next()
        self.assertEqual(cache_value['EPS'], value)
        self.assertEqual(cache_value['date'], date)
        self.assertEqual(cache_value['symbol'], symbol)
        
    def test_cache_miss(self):
        symbol = 'ABC'
        date = datetime.datetime(2012, 12, 1)
        self.mock_db.get.return_value = None
        mock_get_set = mock.Mock()
        self.date_range_cache._get_set = mock_get_set
        self.mock_db.get.return_value = None
        self.date_range_cache.get(symbols=[symbol], dates=[date]).next()
        mock_get_set.assert_called_once_with(symbol=symbol, date=date)

from financial_fundamentals.mongo_drivers import MongoTestCase, MongoIntervalseries
import pytz
class MongoDateRangesIntegrationTestCase(MongoTestCase):
    metric = 'price'
    def setUp(self):
        super(MongoDateRangesIntegrationTestCase, self).setUp()
        self.mock_getter = mock.Mock()
        self.mongo_db = MongoIntervalseries(collection=self.collection,
                                            metric=self.metric)
        self.cache = FinancialDataRangesCache(gets_data=self.mock_getter, 
                                              database=self.mongo_db)
        
    def test_init(self):
        self.assertIs(self.cache._database, self.mongo_db)
    
    def test_set(self):
        price = 100.
        symbol = 'ABC'
        date = datetime.datetime(2012, 12, 15)
        range_start, range_end = datetime.datetime(2012, 12, 1), datetime.datetime(2012, 12, 31)
        self.mock_getter.return_value = (range_start,
                                         price,
                                         range_end)
        value = self.cache.get(symbols=[symbol], dates=[date]).next()
        self.assertEqual(value['price'], price)
        self.assertEqual(value['date'], date.replace(tzinfo=pytz.UTC))
        self.assertEqual(self.collection.find({'start' : range_start,
                                               'end' : range_end,
                                               'symbol' : symbol}).next()['price'], price)
        