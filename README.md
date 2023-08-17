# pyTwitchChatBot
A simple chatbot for Twitch, in python.

Requires Python 3.6+

If you use my code, let me know! I'd love to see what you do with it.

Example usage:

    from chatbot import ChatBot
    my_bot = ChatBot(username, password, channel_name)

    while True:
      new_messages = my_bot.get_messages() # waits for at least one new message to arrive, then returns a list of dicts representing new messages
      for message in new_messages:
        if message["message_type"] == "privmsg":
          user = message["display-name"].lower()
          message_text = message["message"]
