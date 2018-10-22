from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from math import sin, cos, sqrt, atan2, radians
from staticmap import StaticMap, Line
from weather import Weather, Unit
import pandas as pd
import telegram
import catboost
import datetime
import logging
import emoji
import json
import os


# Enable logging.
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - \
                            %(message)s', level=logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

weather = Weather(unit=Unit.CELSIUS)
model = catboost.CatBoostRegressor().load_model('model_fire_pred.uu')

FIRE = emoji.emojize("Fire :fire:", use_aliases=True)
SHARING_LOCATION = "Would you mind sharing your location with me?"
SEND_LOCATION = emoji.emojize("Send location :round_pushpin:", use_aliases=True)
GREETINGS = 'Hi User! The purpose of this bot is to monitor fires around you.'
NEAREST_FIRE = emoji.emojize("Where's nearest fire? :eyes:", use_aliases=True)
SEE_FIRE = emoji.emojize("I see fire! :scream:", use_aliases=True)
WHAT_NEXT = emoji.emojize("What you want to do next? :point_down:", use_aliases=True)
VISUAL = "In visual range"
FAR = "It's far from here"
IMAGE_FILE = 'ferry.png'
PHONENUMBER = '8 (800) 100-94-00'
THANKYOU = 'Thank you for your contribution in firefighting!'
THANKSFORUSAGE = 'Thanks for using this bot. Have a nice day!'

users_locations = dict()


def get_token():
    path = os.path.join('token.json')
    with open(path) as jsn:
        data = json.load(jsn)
    return data['token']


def img_fire(user_coordinates_lat, user_coordinates_lon):
    m = StaticMap(800, 800, 80)

    coordinates = [[min_distance(user_coordinates_lat, user_coordinates_lon)[1][0],
                    min_distance(user_coordinates_lat, user_coordinates_lon)[1][1]]]
    line_outline = Line(coordinates, 'white', 6)
    line = Line(coordinates, '#D2322D', 10)

    m.add_line(line_outline)
    m.add_line(line)

    image = m.render()
    image.save(IMAGE_FILE)


def min_distance(user_lat, user_lon):
    def calculate_distance(lat1, lon1, lat2, lon2):
        # Approximate radius of earth in km.
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
    coor = []
    for i, j in lat_long:
        distance.append(calculate_distance(user_lat, user_lon, i, j))
        coor.append([j, i])

    dist_coor = sorted(list(zip(distance, coor)))

    return dist_coor[0][0], dist_coor[0][1]


def text_handler(bot, update):
    global users_locations

    text = update.message.text
    chat_id = update.message.chat_id

    if str(chat_id) in users_locations:
        location = users_locations[str(chat_id)]

        lookup = weather.lookup_by_latlng(float(location['latitude']), float(location['longitude']))

        is_rain = len([x for x in ['Showers', 'Rain'] if x in lookup.condition.text])
        if is_rain > 0:
            is_rain = 1

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
        # print(sample)
        prediction = model.predict(sample)
        # prediction = [4.0]

        data['firearea'] = round(prediction[0])
        data['nearest'] = round(min_distance(float(location['latitude']), float(location['longitude']))[0])

        if text == FIRE:
            location_keyboard = telegram.KeyboardButton(text=SEND_LOCATION, request_location=True)

            custom_keyboard = [[location_keyboard]]
            reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard)
            bot.send_message(chat_id=chat_id, text=SHARING_LOCATION,
                             reply_markup=reply_markup)
        elif text == SEE_FIRE:
            # в зоне видимости vs где-то далеко
            visual_keyboard = telegram.KeyboardButton(text=VISUAL)
            far_keyboard = telegram.KeyboardButton(text=FAR)

            custom_keyboard = [[visual_keyboard, far_keyboard]]
            reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard)
            bot.send_message(chat_id=chat_id, text="How far from you?", reply_markup=reply_markup)
        elif text == VISUAL:
            # вызвать пожарных?
            yes_keyboard = telegram.KeyboardButton(text='Yes')
            no_keyboard = telegram.KeyboardButton(text='No')

            custom_keyboard = [[yes_keyboard, no_keyboard]]
            reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard)
            bot.send_message(chat_id=chat_id, text="Should we call firefighters?", reply_markup=reply_markup)
        elif text == FAR:
            # вызвать пожарных?
            yes_keyboard = telegram.KeyboardButton(text='Yes')
            no_keyboard = telegram.KeyboardButton(text='No')

            custom_keyboard = [[yes_keyboard, no_keyboard]]
            reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard)
            bot.send_message(chat_id=chat_id, text="Should we call firefighters?", reply_markup=reply_markup)
        elif text == 'Yes':
            if data['firearea'] > 5:
                bot.send_message(chat_id=chat_id, text="Ok, firefighters are on the way!")
                bot.send_message(chat_id=chat_id, parse_mode=telegram.ParseMode.MARKDOWN, text="This fire is very dangerous. Predicted area of fire is about *{}* of hectares. Take care! The number of firefighters is {}".format(data['firearea'], PHONENUMBER))
            else:
                bot.send_message(chat_id=chat_id, text="Ok, firefighters are on the way! Be careful", reply_markup=None)
                bot.send_message(chat_id=chat_id, parse_mode=telegram.ParseMode.MARKDOWN,
                                 text="Predicted area of fire is about *{}* of hectares. Take care! The number of firefighters is {}".format(
                                     data['firearea'], PHONENUMBER))

            thankyou(bot, update)
        elif text == 'No':
            if data['firearea'] > 5:
                bot.send_message(chat_id=chat_id, parse_mode=telegram.ParseMode.MARKDOWN, text="This fire is very dangerous. Predicted area of fire is about *{}* of hectares. Take care! The number of firefighters is {}".format(data['firearea'], PHONENUMBER))
            else:
                bot.send_message(chat_id=chat_id, text="Ok, be careful!", reply_markup=None)
                bot.send_message(chat_id=chat_id, parse_mode=telegram.ParseMode.MARKDOWN,
                                 text="Predicted area of fire is about *{}* of hectares. Take care! The number of firefighters is {}".format(
                                     data['firearea'], PHONENUMBER))

            thankyou(bot, update)
        elif text == NEAREST_FIRE:
            img_fire(float(location['latitude']), float(location['longitude']))

            text = list()
            text.append(emoji.emojize("Nearest fire to you: {} km :fire:".format(data['nearest']), use_aliases=True))
            text.append('---------')
            text.append('Temperature: {} degrees Celsius'.format(data['temp']))
            text.append("Condition: {}".format(data['condition']))
            text.append("Wind's speed: {} km/h".format(data['speed']))
            text.append("Humidity: {} %".format(data['RH']))
            text.append("Visibility: {}".format(data['vis']))

            text = '\n'.join(text)

            bot.send_message(chat_id=chat_id, text=text)
            with open(IMAGE_FILE, 'rb') as file:
                bot.send_photo(chat_id=chat_id, photo=file)

            thanksforusage(bot, update)
        else:
            location_keyboard = telegram.KeyboardButton(text=SEND_LOCATION, request_location=True)
            fire_keyboard = telegram.KeyboardButton(text=FIRE)

            custom_keyboard = [[location_keyboard, fire_keyboard]]
            reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard)
            bot.send_message(chat_id=chat_id, text="How's your day?", reply_markup=reply_markup)
    else:
        bot.send_message(chat_id=chat_id, text="Please send your location")


def location_handler(bot, update):
    global users_locations

    chat_id = update.message.chat_id
    users_locations[str(chat_id)] = update.message.location

    fire_keyboard = telegram.KeyboardButton(text=SEE_FIRE)
    nearest_keyboard = telegram.KeyboardButton(text=NEAREST_FIRE)

    custom_keyboard = [[fire_keyboard, nearest_keyboard]]
    reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard)
    bot.send_message(chat_id=chat_id, text=WHAT_NEXT, reply_markup=reply_markup)


def error(bot, update, error):
    logger.warning('Update "%s" caused error "%s"' % (update, error))


def thankyou(bot, update):
    chat_id = update.message.chat_id

    location_keyboard = telegram.KeyboardButton(text=SEND_LOCATION, request_location=True)
    fire_keyboard = telegram.KeyboardButton(text=FIRE)

    custom_keyboard = [[location_keyboard, fire_keyboard]]
    reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard)
    bot.send_message(chat_id=chat_id, text=THANKYOU, reply_markup=reply_markup)


def thanksforusage(bot, update):
    chat_id = update.message.chat_id

    location_keyboard = telegram.KeyboardButton(text=SEND_LOCATION, request_location=True)
    fire_keyboard = telegram.KeyboardButton(text=FIRE)

    custom_keyboard = [[location_keyboard, fire_keyboard]]
    reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard)
    bot.send_message(chat_id=chat_id, text=THANKSFORUSAGE, reply_markup=reply_markup)


def start(bot, update):
    chat_id = update.message.chat_id

    location_keyboard = telegram.KeyboardButton(text=SEND_LOCATION, request_location=True)
    fire_keyboard = telegram.KeyboardButton(text=FIRE)

    custom_keyboard = [[location_keyboard, fire_keyboard]]
    reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard)
    bot.send_message(chat_id=chat_id, text=GREETINGS, reply_markup=reply_markup)


def run():
    token = get_token()

    req = telegram.utils.request.Request(proxy_url='socks5h://127.0.0.1:9050',
                                         read_timeout=30, connect_timeout=20,
                                         con_pool_size=10)
    bot = telegram.Bot(token=token, request=req)
    updater = Updater(bot=bot)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(MessageHandler(Filters.text, text_handler))
    dp.add_handler(MessageHandler(Filters.location, location_handler))

    dp.add_error_handler(error)
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    run()
