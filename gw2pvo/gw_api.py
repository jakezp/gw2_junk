import json
import logging
import time
from datetime import datetime, timedelta
import requests

__author__ = "Mark Ruys"
__copyright__ = "Copyright 2017, Mark Ruys"
__license__ = "MIT"
__email__ = "mark@paracas.nl"

class GoodWeApi:

    def __init__(self, system_id, account, password):
        self.system_id = system_id
        self.account = account
        self.password = password
        self.token = '{"version":"v3.1","client":"ios","language":"en"}'
        self.global_url = 'https://semsportal.com/api/'
        self.base_url = self.global_url

    def statusText(self, status):
        labels = { -1 : 'Offline', 0 : 'Waiting', 1 : 'Normal', 2: 'Fault' }
        return labels[status] if status in labels else 'Unknown'

    def calcPvVoltage(self, data):
        pv_voltages = [
            data['vpv' + str(i)]
            for i in range(1, 5)
            if 'vpv' + str(i) in data
            if data['vpv' + str(i)]
            if data['vpv' + str(i)] < 6553
        ]
        return round(sum(pv_voltages), 1)

    def getCurrentReadings(self):
        ''' Download the most recent readings from the GoodWe API. '''

        payload = {
            'powerStationId' : self.system_id
        }
        data = self.call("v2/PowerStation/GetMonitorDetailByPowerstationId", payload)

        result = {
            'status' : 'Unknown',
            'pgrid_w' : 0,
            'eday_kwh' : 0,
            'etotal_kwh' : 0,
            'grid_voltage' : 0,
            'pv_voltage' : 0,
            'load' : 0,
            'soc' : 0,
            'buy' : 0,
            'sell' : 0,
            'meter' : 0,
            'consumed_total' : 0,
            'latitude' : data['info'].get('latitude'),
            'longitude' : data['info'].get('longitude')
        }

        count = 0
        for inverterData in data['inverter']:
            status = self.statusText(inverterData['status'])
            if status == 'Normal':
                result['status'] = status
                result['pgrid_w'] += inverterData['out_pac']
                result['grid_voltage'] += self.parseValue(inverterData['output_voltage'], 'V')
                result['pv_voltage'] += self.calcPvVoltage(inverterData['d'])
                result['load'] += self.parseValue(data['powerflow']['load'], '(W)')
                count += 1
            result['eday_kwh'] += inverterData['eday']
            result['etotal_kwh'] += inverterData['etotal']
            result['buy'] += inverterData['invert_full']['buy']
            result['sell'] += inverterData['invert_full']['seller']
            result['soc'] += float(data['powerflow']['soc'])
            result['consumed_total'] += round(data['energeStatisticsCharts']['consumptionOfLoad'], 2)
        if count > 0:
            # These values should not be the sum, but the average
            result['grid_voltage'] /= count
            result['pv_voltage'] /= count
            result['soc'] /= count
        elif len(data['inverter']) > 0:
            # We have no online inverters, then just pick the first
            inverterData = data['inverter'][0]
            result['status'] = self.statusText(inverterData['status'])
            result['pgrid_w'] = inverterData['out_pac']
            result['grid_voltage'] = self.parseValue(inverterData['output_voltage'], 'V')
            result['pv_voltage'] = self.calcPvVoltage(inverterData['d'])
            result['load'] = self.parseValue(data['powerflow']['load'], '(W)')

        message = "Status: {status}, Current PV power: {pgrid_w} W now, Current consumption: {load} kW now, Current grid voltage: {grid_voltage} V, Current PV voltage: {pv_voltage} V, Total PV power generated today: {eday_kwh} kWh, Total consumption today: {consumed_total} kWh, Total power bought today: {buy} kWh; Total power sold today: {sell} kWh, Current battery SOC: {soc} %, All time total generation: {etotal_kwh} kWh all time".format(**result)
        if result['status'] == 'Normal' or result['status'] == 'Offline':
            logging.info(message)
        else:
            logging.warning(message)

        return result

    def getActualKwh(self, date):
        payload = {
            'powerstation_id' : self.system_id,
            'count' : 1,
            'date' : date.strftime('%Y-%m-%d')
        }
        data = self.call("v2/PowerStationMonitor/GetPowerStationPowerAndIncomeByDay", payload)
        if not data:
            logging.warning("GetPowerStationPowerAndIncomeByDay missing data")
            return 0

        eday_kwh = 0
        for day in data:
            if day['d'] == date.strftime('%m/%d/%Y'):
                eday_kwh = day['p']

        return eday_kwh

    def getActualConsumption(self, date, index):
        payload = {
            'id' : self.system_id,
            'date' : date.strftime('%Y-%m-%d'),
            'range' : 2,
            'chartIndexId' : index,
            'isDetailFull' : ''
        }
        data = self.call("v2/Charts/GetChartByPlant", payload)
        if 'modelData' not in data:
                logging.warning("GetChartByPlant returned bad data: " + str(data))
                return []
        logging.debug(str(data['modelData']['consumptionOfLoad']))
        
        return data['modelData']['consumptionOfLoad']

#    def getActualConsumption(self, date):
#        data = self.getDayLoad(date, 7)
#        print(data)
#        energy_used = data['modelData']['consumptionOfLoad']
#        logging.debug(str(energy_used))

#        ireturn energy_used

    def getLocation(self):
        payload = {
            'powerStationId' : self.system_id
        }
        data = self.call("v2/PowerStation/GetMonitorDetailByPowerstationId", payload)
        if 'info' not in data:
            logging.warning("GetMonitorDetailByPowerstationId returned bad data: " + str(data))
            return {}

        return {
            'latitude' : data['info'].get('latitude'),
            'longitude' : data['info'].get('longitude'),
        }

    def getDayPac(self, date):
        payload = {
            'id' : self.system_id,
            'date' : date.strftime('%Y-%m-%d')
        }
        data = self.call("v2/PowerStationMonitor/GetPowerStationPacByDayForApp", payload)
        if 'pacs' not in data:
            logging.warning("GetPowerStationPacByDayForApp returned bad data: " + str(data))
            return []

        return data['pacs']

    def getDayLoad(self, date, index):
        payload = { 
            'id' : self.system_id,
            'date' : date.strftime('%Y-%m-%d'),
            'range' : 2,
            'chartIndexId' : index,
            'isDetailFull' : ''
        }
        data = self.call("v2/Charts/GetChartByPlant", payload)
        if 'lines' not in data:
                logging.warning("GetChartByPlant returned bad data: " + str(data))
                return []

        return data['lines'][3]['xy']

    def getDayReadings(self, date):
        result = self.getLocation()
        pacs = self.getDayPac(date)
        xy = self.getDayLoad(date, 1)
        hours = 0
        kwh = 0
        c_kwh = 0
        result['entries'] = []
        
        for p, x in zip(pacs, xy):
            parsed_date = datetime.strptime(p['date'], "%m/%d/%Y %H:%M:%S")
            next_hours = parsed_date.hour + parsed_date.minute / 60

            pgrid_w = p['pac']
            load = x['y']
            if pgrid_w >= 0:
                kwh += pgrid_w / 1000 * (next_hours - hours)
                c_kwh += load /1000 * (next_hours - hours)
                result['entries'].append({
                    'dt' : parsed_date,
                    'pgrid_w': pgrid_w,
                    'load': load,
                    'eday_kwh': round(kwh, 3),
                    'energy_used' : round(c_kwh, 3)
                })
            hours = next_hours
            #print("pgrid_w = " + str(pgrid_w) + ", kwh = " + str(kwh) + ", load = " + str(load) + ", c_kwh = " + str(c_kwh) + ", eday_kwh = " + str(result['entries']['eday_kwh']) + ", energy_used = "  + str(result['entries']['energy_used']))

#        for sample in pacs:
#            parsed_date = datetime.strptime(sample['date'], "%m/%d/%Y %H:%M:%S")
#            next_hours = parsed_date.hour + parsed_date.minute / 60
            
#            pgrid_w = sample['pac']
#            if pgrid_w > 0:
#                kwh += pgrid_w / 1000 * (next_hours - hours)
#                pv_result.append({
#                    'dt' : parsed_date,
#                    'pgrid_w': pgrid_w,
#                    'eday_kwh': round(kwh, 3)
#                })
#            hours = next_hours
#
#
#        for sample in xy:
#            date_string = str(date.strftime('%Y-%m-%d')) + " " + sample['x']
#            parsed_date = datetime.strptime(date_string, "%Y-%m-%d %H:%M")
#            next_hours = parsed_date.hour + parsed_date.minute / 60
#
#            load = sample['y']
#            if load > 0:
#                c_kwh += load /1000 * (next_hours - hours)
#                load_result.append({
#                    #'dt' : parsed_date,
#                    'load' : load,
#                    'energy_used' : round(c_kwh, 3)
#                })
#            hours = next_hours

        eday_kwh = self.getActualKwh(date)
        if eday_kwh > 0:
            correction = eday_kwh / kwh
            for sample in result['entries']:
                logging.debug(sample['eday_kwh'])
                sample['eday_kwh'] *= correction
                logging.debug(sample['eday_kwh'])
        
        energy_used = self.getActualConsumption(date, 7)
        if  energy_used > 0:
            c_correction = energy_used / c_kwh
            for sample in result['entries']:
                logging.debug(sample['energy_used'])
                sample['energy_used'] *= c_correction
                logging.debug(sample['energy_used'])

        
        print("actual eday_kwh = " + str(eday_kwh) + " , kwh = " + str(kwh))
        print("actual energy_used = " + str(energy_used) + " , c_kwh = " + str(kwh))

        return result

    def call(self, url, payload):
        for i in range(1, 4):
            try:
                headers = {
                    'User-Agent': 'SEMS Portal/3.1 (iPhone; iOS 13.5.1; Scale/2.00)',
                    'Token': self.token,
                }

                r = requests.post(self.base_url + url, headers=headers, data=payload, timeout=10)
                r.raise_for_status()
                data = r.json()
                logging.debug(json.dumps(data, indent=4, sort_keys=True))
                #print(json.dumps(payload, indent=4, sort_keys=True))

                try:
                    code = int(data['code'])
                except ValueError:
                    raise Exception("Failed to call GoodWe API (no code)")

                if code == 0 and data['data'] is not None:
                    return data['data']
                elif code == 100001:
                    loginPayload = {
                        'account': self.account,
                        'pwd': self.password,
                    }
                    r = requests.post(self.global_url + 'v2/Common/CrossLogin', headers=headers, data=loginPayload, timeout=10)
                    r.raise_for_status()
                    data = r.json()
                    if 'api' not in data:
                        raise Exception(data['msg'])
                    self.base_url = data['api']
                    self.token = json.dumps(data['data'])
                else:
                    raise Exception("Failed to call GoodWe API (code {})".format(code))
            except requests.exceptions.RequestException as exp:
                logging.warning(exp)
            time.sleep(i ** 3)
        else:
            raise Exception("Failed to call GoodWe API (too many retries)")

        return {}

    def parseValue(self, value, unit):
        try:
            return float(value.rstrip(unit))
        except ValueError as exp:
            logging.warning(exp)
            return 0
