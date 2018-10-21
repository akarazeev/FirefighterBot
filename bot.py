from telegram.ext import Updater, MessageHandler, Filters
from math import sin, cos, sqrt, atan2, radians
from weather import Weather, Unit
import catboost
import datetime
import pandas as pd
import telegram
import emoji
import subprocess
import logging
import json
import os


# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - \
                            %(message)s', level=logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


weather = Weather(unit=Unit.CELSIUS)
model = catboost.CatBoostRegressor().load_model('model_fire_pred.uu')


def get_token():
    path = os.path.join('token.json')
    with open(path) as jsn:
        data = json.load(jsn)
    return data['token']


def min_distance(user_lat, user_lon):
    def calculate_distance(lat1, lon1, lat2, lon2):
        # approximate radius of earth in km
        R = 6373.0

        lat1 = radians(lat1)
        lon1 = radians(lon1)
        lat2 = radians(lat2)
        lon2 = radians(lon2)

        dlon = lon2 - lon1
        dlat = lat2 - lat1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        distance = R * c

        return distance

    data_distance = pd.read_csv('MODIS_C6_Russia_and_Asia_24h.csv')
    lat_long = list(zip(data_distance['latitude'], data_distance['longitude']))
    distance = []
    for i, j in lat_long:
        distance.append(calculate_distance(user_lat, user_lon, i, j))

    return min(distance)


def text_handler(bot, update):
    text = update.message.text
    update.message.reply_text("echo: {}".format(text))


def location_handler(bot, update):
    location = update.message.location
    lookup = weather.lookup_by_latlng(float(location['latitude']), float(location['longitude']))

    is_rain = len([x for x in ['Showers', 'Rain'] if x in lookup.condition.text])
    if is_rain > 0:
        is_rain = 1

    # datetime.datetime.strptime(location.condition.date, '%a, %d %b %Y %H:%M %p MSK')

    date = lookup.condition.date.split()[1:3]
    date = ' '.join(date)
    date = datetime.datetime.strptime(date, '%d %b')

    data = dict()
    data['month'] = date.month
    data['day'] = date.day

    data['rain'] = is_rain
    data['temp'] = lookup.condition.temp
    data['condition'] = lookup.condition.text
    data['speed'] = lookup.wind.speed
    data['RH'] = lookup.atmosphere.humidity
    data['vis'] = lookup.atmosphere.visibility

    # month, day, temp, RH, wind, rain
    sample = {
        'row1': [data['month'], data['day'], data['temp'], data['RH'], data['speed'], data['rain']]
    }
    sample = pd.DataFrame.from_dict(sample, orient='index')
    prediction = model.predict(sample)

    data['firearea'] = round(prediction[0])
    data['nearest'] = round(min_distance(float(location['latitude']), float(location['longitude'])))

    text = list()
    text.append('Temperature: {}'.format(data['temp']))
    text.append("Condition: {}".format(data['condition']))
    text.append("Wind's speed: {} km per h".format(data['speed']))
    text.append("Humidity: {} %".format(data['RH']))
    text.append("Visibility: {}".format(data['vis']))
    text.append("Rain: {}".format(data['rain']))
    text.append("Predicted area of fire: {}".format(data['firearea']))
    text.append(emoji.emojize("Nearest fire to you: {} :fire:".format(data['nearest']), use_aliases=True))
    text.append('---------')

    if prediction > 10:
        text.append(emoji.emojize(':fire:', use_aliases=True))
    else:
        text.append(emoji.emojize(':smile:', use_aliases=True))

    text = '\n'.join(text)

    update.message.reply_text(text)


def error(bot, update, error):
    logger.warning('Update "%s" caused error "%s"' % (update, error))


def run():
    token = get_token()

    req = telegram.utils.request.Request(proxy_url='socks5://127.0.0.1:9050',
                                         read_timeout=30, connect_timeout=20,
                                         con_pool_size=10)
    bot = telegram.Bot(token=token, request=req)
    updater = Updater(bot=bot)
    dp = updater.dispatcher

    # On noncommand i.e message - echo the message on Telegram.
    dp.add_handler(MessageHandler(Filters.text, text_handler))
    dp.add_handler(MessageHandler(Filters.location, location_handler))

    dp.add_error_handler(error)
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    run()
