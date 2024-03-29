from socket import socket
from time   import time, sleep

class NotInitialisedException(Exception):
	def __init__(self, args):
		if args:
			self.message = args[0]
		else:
			self.message = None

class ChatBot():
	"""
	Creates a chatbot which can send and receive messages in a Twitch channel's chat.

	Params (required):

	username - the username of the Bot
	password - the password or oauth token (see https://dev.twitch.tv/docs/authentication)
	channel  - the channel whose chat the bot will interact with

	Keyword Args (optional):

	debug=True      (default: False) - print debug messages to console
	capabilities=[] (default: empty) - a list of lowercase strings of additional capabilities to request - see https://dev.twitch.tv/docs/irc/guide/#twitch-irc-capabilities
	
	"""

	def __init__(self, username, password, channel, **kwargs):
		self.initialised = False
		
		self.username = username.lower()
		self.password = password
		self.channel  = channel.lower()

		self.requested_capabilities = []
		self.granted_capabilities = []

		if "debug" in kwargs:
			# only set debug mode if the debug flag is explicitly True, i.e. not for truthy objects such as non-empty strings.
			self.debug = kwargs["debug"] is True 
			if self.debug:
				print(f"Debugging is turned on.")
		else:
			self.debug = False

		if "capabilities" in kwargs:
			if "tags" in kwargs["capabilities"]:
				self.requested_capabilities.append("tags")
				if self.debug:
					print("Requesting tags capability")
			if "membership" in kwargs["capabilities"]:
				self.requested_capabilities.append("membership")
				if self.debug:
					print("Requesting membership capability")
			if "commands" in kwargs["capabilities"]:
				self.requested_capabilities.append("commands")
				if self.debug:
					print("Requesting commands capability")
		self._open_socket()

	def _open_socket(self):
		self.socket = socket()
		self.socket.connect(("irc.twitch.tv", 6667))

		opening_request = "PASS {password}\r\nNICK {username}\r\nJOIN #{channel}\r\n"

		if self.requested_capabilities:
			if "tags" in self.requested_capabilities:
				opening_request += "CAP REQ :twitch.tv/tags\r\n"
			if "membership" in self.requested_capabilities:
				opening_request += "CAP REQ :twitch.tv/membership\r\n"
			if "commands" in self.requested_capabilities:
				opening_request += "CAP REQ :twitch.tv/commands\r\n"

		opening_request = opening_request.format(password=self.password, username=self.username, channel=self.channel).encode("utf-8")
		self.socket.send(opening_request)

		readbuffer = ""
		success = False

		while not success:
			next_bytes = self.socket.recv(4096).decode("utf-8")
			readbuffer += str(next_bytes)
			response_lines = readbuffer.split("\r\n")

			if response_lines == [""]: # this happens sometimes
				raise NotInitialisedException("Unable to log into Twitch: no response received.")

			for line in response_lines:
				if self.debug:
					print(line)
				if "Invalid NICK" in line:
					raise NotInitialisedException("Unable to log into Twitch: invalid username.")
				elif "Improperly formatted auth" in line:
					raise NotInitialisedException("Unable to log into Twitch: login details are incorrect.")

				if "CAP * ACK :twitch.tv/membership" in line:
					self.granted_capabilities.append("membership")
					if self.debug:
						print("Membership capability granted.")
				if "CAP * ACK :twitch.tv/commands" in line:
					self.granted_capabilities.append("commands")
					if self.debug:
						print("Commands capability granted.")
				if "CAP * ACK :twitch.tv/tags" in line:
					self.granted_capabilities.append("tags")
					if self.debug:
						print("Tags capability granted.")
				if "End of /NAMES list" in line: # keep loading until end of names list
					success = True

		# Sometimes the above will initialise the bot completely.
		# However if Capabilities are requested, sometimes they can come through in the wrong order
		# So if we've not heard back the ACK for all of the requested capabilities, we try another receive:

		if len(self.requested_capabilities) != len(self.granted_capabilities): # not all requesed capabilities are granted
			next_bytes = self.socket.recv(4096).decode("utf-8")
			readbuffer += str(next_bytes)
			response_lines = readbuffer.split("\r\n") # this might contain the first chat message - if so it won't be processed.

			for line in response_lines:
				if self.debug:
					print(line)
				if "CAP * ACK :twitch.tv/membership" in line:
					self.granted_capabilities.append("membership")
					if self.debug:
						print("Membership capability granted (on second receive).")
				if "CAP * ACK :twitch.tv/commands" in line:
					self.granted_capabilities.append("commands")
					if self.debug:
						print("Commands capability granted (on second receive).")
				if "CAP * ACK :twitch.tv/tags" in line:
					self.granted_capabilities.append("tags")
					if self.debug:
						print("Tags capability granted (on second receive).")

		self.initialised = True

	def get_messages(self):
		"""
		Receives new messages from chat.
		
		Returns a list of new messages added to chat since the last call to this function, or since bot was initialised.
		Each message object in the returned list is a dict of message metadata.
		Metadata in the message dict includes: message_type, display-name, message, badges, and more.
		message_type is "privmsg" for chat messages or "notice" for channel notices. Twitch may send other message types too.
		See https://dev.twitch.tv/docs/irc/commands for "command" message types (only sent if "commands" capability is enabled)
		This function will listen for new messages and only return after a new message is received in the chat.
		"""

		#if not self.initialised:
		#	raise NotInitialisedException("The chatbot must be initialised before a message can be sent.")

		try:
			next_bytes = self.socket.recv(4096).decode("utf-8")
		except AttributeError:
			raise NotInitialisedException("The chatbot must be initialised before messages can be received.")
			
		lines = next_bytes.split("\r\n")

		messages = []

		for line in lines:
			if self.debug:
				print(line)

			if line == "":
				continue

			if line[:4] == "PING":
				self.send_pong()
				continue

			"""
			As this uses "if x in line" to detect message types, in theory someone could send a message in chat saying
			 e.g. "hey guys tmi.twitch.tv NOTICE #", so that line would have both PRIVMSG and (e.g.) "tmi.twitch.tv NOTICE #"
			in it. By checking for PRIVMSG first, no matter the content of the message it will always be processed as a chat 
			message. Kind of like sanitising it. Sort of.
			"""

			message_dict = None # will be set to a dict below if message type is recognised

			if "tmi.twitch.tv PRIVMSG #" in line: # chat message from user (other message types are possible e.g. NOTICE)
				message_dict = {"message_type":"privmsg"}

				try:
					if "tags" in self.granted_capabilities and line[0] == "@":
						line = line[1:] # remove the @ from the beginning

						# first section is all tags except last one, then we add the last one to the list by a different method
						msg_tags = (";".join(line.split("PRIVMSG")[0].split(";")[:-1]) + ";" + (line.split("PRIVMSG")[0].split(":")[-2]).split(";")[-1]).split(";") # dumb that I have to do this
						for tag in msg_tags:
							if "=" in tag:
								key, val = tag.split("=")
								message_dict[key.strip()] = val.strip()
					else:
						start_of_name = line.index(":") + 1
						end_of_name = line.index("!")
						username = line[start_of_name:end_of_name].lower()
						if 4 <= len(username) <= 25: # min and max lengths for username.. just a sanity check
							message_dict["display-name"] = username
						else:
							raise ValueError("Unable to find username in line.")
					message_dict["message"] = ":".join(line.split("PRIVMSG")[1].split(":")[1:]) # everything after the PRIVMSG.. then after the subsequent colon
				except (ValueError, IndexError) as ex:
					if self.debug:
						print(f"Unable to parse line as message: \n\n{line} \n\n{str(ex)}")
					continue # bad line

			elif "tmi.twitch.tv NOTICE #" in line:
				"""Example NOTICE message: @msg-id=color_changed :tmi.twitch.tv NOTICE #kaywee :Your color has been changed."""
				message_dict = {"message_type":"notice"}
				line = line[1:] # remove the @ from the beginning
				message_dict["msg_id"]  = line.split(":")[0][:-1].split("=")[1]
				message_dict["message"] = line.split(":")[-1]

			elif "tmi.twitch.tv USERNOTICE #" in line:
				message_dict = {"message_type":"usernotice"}
				line = line[1:] # remove leading @
				msg_tags = (";".join(line.split("USERNOTICE")[0].split(";")[:-1]) + ";" + (line.split("USERNOTICE")[0].split(":")[-2]).split(";")[-1]).split(";") # dumb that I have to do this

				for tag in msg_tags:
					if "=" in tag: # sanity check - all should have key=value
						key, val = tag.split("=")
						message_dict[key.strip()] = val.strip()

			elif ":tmi.twitch.tv USERSTATE" in line:
				"""Example message:
				@badge-info=subscriber/7;badges=moderator/1,subscriber/6;color=#FF69B4;display-name=RoboKaywee;
				emote-sets=0,300374282,300542926,537206155,564265402,592920959,610186276;mod=1;subscriber=1;user-type=mod :tmi.twitch.tv USERSTATE #kaywee
				"""
				message_dict = {"message_type":"userstate"} # what info comes with this?

				line = line[1:] # remove leading @
				msg_tags = (";".join(line.split("USERSTATE")[0].split(";")[:-1]) + ";" + (line.split("USERSTATE")[0].split(":")[-2]).split(";")[-1]).split(";") # dumb that I have to do this

				for tag in msg_tags:
					if "=" in tag: # sanity check - all should have key=value
						key, val = tag.split("=")
						message_dict[key.strip()] = val.strip()

			elif ":tmi.twitch.tv HOSTTARGET" in line:
				target = line.split(":")[2].split(" ")[0]
				if target not in ["-", ""]:
					viewers = line.split(":")[2].split(" ")[1]
					message_dict = {"message_type":"hosttarget", "host_target": target, "viewers": viewers}

			elif ":tmi.twitch.tv RECONNECT" in line: # a command to reconnect to chat
				self.reset_socket() # reconnect to chat per twitch's request
				continue # don't return this as a message type

			elif ":tmi.twitch.tv CLEARMSG" in line: # single message was deleted
				message_dict = {"message_type":"clearmsg"} 
				if "tags" in self.granted_capabilities and line[0] == "@":
					msg_tags = line[1:].split(":tmi.twitch.tv CLEARMSG")[0].split(";")
					for tag in msg_tags:
						if "=" in tag:
							key, val = tag.split("=")
							message_dict[key.strip()] = val.strip()

			elif ":tmi.twitch.tv CLEARCHAT" in line: # clear all messages from user
				message_dict = {"message_type":"clearchat"}
				if "tags" in self.granted_capabilities and line[0] == "@":
					msg_tags = line[1:].split(":tmi.twitch.tv CLEARCHAT")[0].split(";")
					for tag in msg_tags:
						if "=" in tag: # sanity check - all should have key=value
							key, val = tag.split("=")
							message_dict[key.strip()] = val.strip()

			elif ":tmi.twitch.tv ROOMSTATE" in line:
				"""Example message:
				@room-id=136108665;subs-only=0 :tmi.twitch.tv ROOMSTATE #kaywee
				"""
				message_dict = {"message_type":"roomstate"}
				line = line[1:] # remove leading @

				msg_tags = (";".join(line.split("ROOMSTATE")[0].split(";")[:-1]) + ";" + (line.split("ROOMSTATE")[0].split(":")[-2]).split(";")[-1]).split(";") # dumb that I have to do this

				for tag in msg_tags:
					if "=" in tag: # sanity check - all should have key=value
						key, val = tag.split("=")
						message_dict[key.strip()] = val.strip()

			elif line.startswith("@badge-info="):
				message_dict = {"message_type":"badge-info"}
				line = line[12:] # remove leading "@badge-info="

				msg_tags = line.split(";")
				for tag in msg_tags:
					if "=" in tag: # sanity check - all should have key=value
						key, val = tag.split("=")
						message_dict[key.strip()] = val.strip()

			else:
				with open("verbose log.txt", "a", encoding="utf-8") as f:
					f.write("Unrecognised line received in Chatbot: " + str(line) + "\n\n")

			if message_dict is not None:
				messages.append(message_dict)

		return messages

	def send_message(self, msg):
		"""Send a message to the channel."""

		msg = msg.replace("\n", " ").replace("\r", "")
		if len(msg) < 500:
			bytes_message = ("PRIVMSG #" + self.channel + " :" + msg + "\r\n").encode('utf-8')
			self.socket.send(bytes_message)
		else:
			chr_limit = 495
			
			chunks = [msg[i:i+chr_limit] for i in range(0, len(msg), chr_limit)]
			for chunk in chunks:
				bytes_message = ("PRIVMSG #" + self.channel + " :" + chunk + "\r\n").encode('utf-8')

				try:
					self.socket.send(bytes_message)
					sleep(0.2)
				except AttributeError:
					raise NotInitialisedException("The chatbot must be initialised before a message can be sent.")

	def send_pong(self):
		msg = "PONG :tmi.twitch.tv\r\n".encode('utf-8')
		self.socket.send(msg)
		if self.debug:
			print("Sent pong.")

	def reset_socket(self):
		"""Re-creates the socket object"""
		del self.socket
		self._open_socket()
