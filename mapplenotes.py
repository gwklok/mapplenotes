#!/usr/bin/env python
import imaplib
import sys
import email
import os
from subprocess import Popen, PIPE, STDOUT
import time
import dateutil.parser
from tempfile import NamedTemporaryFile
import cmd
import getpass
from email.message import Message
import rfc822 

def html_to_text(html):
        process = Popen(["/opt/local/bin/lynx", "-stdin", "-dump",
                                    "-nolist", "-nonumbers"],
                                   shell=False, stdin=PIPE,
                                   stdout=PIPE,
                                   stderr=STDOUT)
        
        #convert binary data to a utf-8 string
        result = process.communicate(input=html)[0].decode("utf-8")
        return result

def get_first_text_block(email_message_instance):
    maintype = email_message_instance.get_content_maintype()
    if maintype == 'multipart':
        for part in email_message_instance.get_payload():
            if part.get_content_maintype() == 'text':
                return part.get_payload()
    elif maintype == 'text':
        return email_message_instance.get_payload()

def compare_message_tuple(x, y):
        if 'date' in x[1] and 'date' in y[1]:
                at = dateutil.parser.parse(x[1]['Date'])
                bt = dateutil.parser.parse(y[1]['Date'])
                return at < bt
        elif 'date' in x[1]:
                return 1
        elif 'date' in y[1]:
                return -1

def edit_note(filehandle):
        foo = ""
        editor = os.getenv('EDITOR', 'vim')
        x = os.spawnlp(os.P_WAIT,editor,editor,filehandle.name)
        if x != 0:
                print "ERROR"
        else:
                fd = open(filehandle.name, "r")
                foo = fd.read()
                print "%s" % foo 
        return foo

class NoteManager(cmd.Cmd):
        _username = ""
        _password = ""
        _hostname = ""
        _conn = None

        def __init__(self, hostname, username, password):
                cmd.Cmd.__init__(self)
                self._username = username
                self._password = password
                self._hostname = hostname

        def connect(self):
                if not self._conn:
                        self._conn = imaplib.IMAP4_SSL(self._hostname)
                        self._conn.login(self._username, self._password)
       
        def _get_ids(self):
                self.connect()
                self._conn.select('Notes')
                result, data = self._conn.uid('search', None, "ALL")

                note_id_list = data[0].split()
                return note_id_list

        def _get_notes(self):
                self.connect()

                self._conn.select('Notes')
                result, data = self._conn.uid('search', None, "ALL")

                note_id_list = data[0].split()
                note_list = []
                for nid in note_id_list:
                        mresult, mdata = self._conn.uid('fetch', nid, '(RFC822)')
                        raw_email = mdata[0][1]
                        email_message = email.message_from_string(raw_email)
                        note_list.append([nid, email_message])
                return note_list

        def parse_args(self, line):
                print line
                return line.split(' ')[2:]

        def do_list(self, line):
                """list
                        list notes"""
                self.connect()
                note_list = self._get_notes()

                #sorted (note_list, cmp=compare_message_tuple)

                for noteid,note in note_list:
                        raw_body = get_first_text_block(note)
                        body = html_to_text(raw_body)
                        print "[%s]-(%s - %s)--\n%s" % (noteid, note['Subject'],
                                                        note['Date'], body)
	def do_delete(self, line):
		self.connect()
		note_list = self._get_notes()
		nid = int(line)
                self._conn.select('Notes')
		self._conn.uid('fetch', nid, '(RFC822)')

	def do_edit(self, line):
                self.connect()
		nid = int(line)
                note_list = self._get_notes()
                for noteid,note in note_list:
			if noteid == nid:
				raw_body = get_first_text_block(note)
				body = html_to_text(raw_body)
				fd = NamedTemporaryFile()
				efd = open(filehandle.name, "w")
				efd.write(body)
				note_contents = edit_note(fd)
				#imap update message contents	
				note.set_payload(note_contents)

        def do_new(self, line):
                """new subject
                        create a new not"""
               
                if len(line) < 1:
                        print "Note needs a subject"
                        return

                fd = NamedTemporaryFile()
                note_contents = edit_note(fd)

                ids = self._get_ids()
                
                #print "%s\n%s" % (line, note_contents)
                new_message = email.message.Message()
                new_message['Subject'] = line
                #new_message['From'] = "%s@%s" % (self._username, self._hostname)
                new_message['From'] = "gwk@gwk.ca"
                new_message['Mime-Version'] = '1.0 (Apple Message framework v1278)'
                new_message['X-Apple-Mail-Remote-Attachments'] = 'YES'
                new_message['Content-Transfer-Encoding'] = '7bit'
                new_message['X-Uniform-Type-Identifier'] = 'com.apple.mail-note'
                new_message['X-Apple-Base-Url'] = "x-msg://%d/" % (int(ids[-1])+1)
                new_message['Date'] = rfc822.formatdate(time.time())
                new_message.set_payload(note_contents)

                self.connect()
                self._conn.append('Notes', '', imaplib.Time2Internaldate(time.time()), str(new_message))
                

def main():
        if len(sys.argv) < 2:
                print "You must supply the hostname of your mail server"
                exit(0)

        hostname = sys.argv[1]        
        sys.stdout.write("Username: ")
        username = raw_input()

        password = getpass.getpass("Password: ")
       
        nm = NoteManager(hostname, username, password)        

        nm.cmdloop()

if __name__ == "__main__":
	main()
