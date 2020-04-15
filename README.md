# pyTwitchBot
A simple chatbot for Twitch, in python.

If you use my code, let me know! I'd love to see what you do with it.

Example usage:

    from chatbot import ChatBot
    my_bot = ChatBot(username, password, channel_name)

    while True:
      new_messages = my_bot.get_messages()
      for username, message in new_messages:
        send_response(username, message)
