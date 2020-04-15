# pyTwitchBot
A simple chatbot for Twitch, in python.

Example usage:

from chatbot import ChatBot
my_bot = ChatBot(username, password, channel_name)

while True:
  new_messages = my_bot.get_messages()
  for username, message in new_messages:
    send_response(username, message)
