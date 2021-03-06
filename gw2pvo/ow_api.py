from datetime import datetime
import logging
import time
import requests

__author__ = "Michaël Hompus"
__copyright__ = "Copyright 2018, Michaël Hompus"
__license__ = "MIT"
__email__ = "michael@hompus.nl"

class OpenWeatherApi:
    def __init__(self, api_key):
        self.api_key = api_key

    def get_temperature(self, latitude, longitude):
        if latitude is None or longitude is None:
            return None

        data = {
            'apiKey' : self.api_key,
            'latitude' : latitude,
            'longitude' : longitude
        }

        #url = "https://api.darksky.net/forecast/{apiKey}/{latitude},{longitude}?units=si&exclude=minutely,hourly,daily,alerts,flags".format(**data)
        url = "https://api.openweathermap.org/data/2.5/onecall?lat={latitude}&lon={longitude}&units=metric&exclude=minutely,hourly,daily,alerts&appid={apiKey}".format(**data)

        for i in range(1, 4):
            try:
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                result = r.json()

                logging.debug(result['current'])
                return result['current']['temperature']

            except requests.exceptions.RequestException as arg:
                logging.warning(arg)
            time.sleep(i ** 3)
        else:
            logging.error("Failed to call Open Weather API")

    def get_temperature_for_day(self, latitude, longitude, date):
        if latitude is None or longitude is None:
            return None

        data = {
            'apiKey' : self.api_key,
            'latitude' : latitude,
            'longitude' : longitude,
            'date' : date.strftime('%s'),
        }

        #url = "https://api.darksky.net/forecast/{apiKey}/{latitude},{longitude},{date}?units=si&exclude=minutely,currently,daily,alerts,flags".format(**data)
        url = "https://api.openweathermap.org/data/2.5/onecall/timemachine?lat={latitude}&lon={longitude}&units=metric&dt={date}&appid={apiKey}".format(**data)

        for i in range(1, 4):
            try:
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                result = r.json()

                logging.debug(result['hourly'])
                return result['hourly']
            except requests.exceptions.RequestException as arg:
                logging.warning(arg)
            time.sleep(i ** 3)
        else:
            logging.error("Failed to call Open Weather API")
