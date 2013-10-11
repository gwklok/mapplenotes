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
import ConfigParser
from os.path import expanduser
import traceback

def html_to_text(html):
    process = Popen(["/opt/local/bin/lynx", "-stdin", "-dump",
                    "-nolist", "-nonumbers"], shell=False, stdin=PIPE, 
                    stdout=PIPE, stderr=STDOUT)
        
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
    return foo

class NoteManager(cmd.Cmd):
    _username = ""
    _password = ""
    _hostname = ""
    _mail_from = ""
    _conn = None

    def __init__(self, hostname, username, mail_from):
        cmd.Cmd.__init__(self)
        self._username = username
        self._hostname = hostname
        self._mail_from = mail_from

    def connect(self):
        if not self._conn:
            try:
                self._conn = imaplib.IMAP4_SSL(self._hostname)
                self._conn.login(self._username, self._password)
            except Exception, ex:
                self._conn = None
                raise ex
    
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

    def set_password(self, password):
        self._password = password

    def parse_args(self, line):
        print line
        return line.split(' ')[2:]

    def do_exit(self, line):
        """exit
        quit mapplenotes"""
        exit(0)

    def do_quit(self, line):
        """quit
        quit mapplenotes"""
        exit(0)

    def do_list(self, line):
        """list 
        list notes"""
        self.connect()
        note_list = self._get_notes()

        for noteid,note in note_list:
            raw_body = get_first_text_block(note)
            body = html_to_text(raw_body)
            print "[%s]-(%s - %s)--\n%s" % (noteid, note['Subject'], 
                                            note['Date'], body)
    def do_delete(self, line):
        """delete
        delete a note by id"""
        if not line:
            return "Must provide a note id"
        self.connect()
        note_list = self._get_notes()
        try:
            nid = int(line)
        except ValueError:
            return "Note id should be an integer value"
        try:
            self._remove_msg(nid)
        except Exception, ex:
            print "Could not find the requested message for deletion"

    def _remove_msg(self, uid):
        self._conn.select('Notes')
        status, msg_ids = self._conn.search(None, 'UID', uid)

        if status != 'OK':
            raise Exception("Could not find uid %d" % uid) 
        else:
            for msg_id in msg_ids[0].split():
                self._conn.store(msg_id, '+FLAGS', r'(\Deleted)')

            typ, response = self._conn.expunge()

    def do_edit(self, line):
        """edit noteid
        Edit note with id noteid
        """
        self.connect()
        nid = int(line)
        note_list = self._get_notes()
        for noteid,note in note_list:
            if int(noteid) == nid:
                print "found it"
                raw_body = get_first_text_block(note)
                body = html_to_text(raw_body)
                fd = NamedTemporaryFile()
                efd = open(fd.name, "w")
                efd.write(body)
                efd.flush()
                efd.close()
                note_contents = edit_note(fd)
                note.set_payload(note_contents)
                self._remove_msg(noteid)
                self._conn.append('Notes', '', 
                                  imaplib.Time2Internaldate( time.time()), 
                                  str(note))
    def do_new(self, line):
        """new subject 
        create a new note"""

        if len(line) < 1:
                print "Note needs a subject"
                return

        fd = NamedTemporaryFile()
        note_contents = edit_note(fd)

        ids = self._get_ids()

        #print "%s\n%s" % (line, note_contents)
        new_message = email.message.Message()
        new_message['Subject'] = line
        new_message['From'] = self._mail_from
        new_message['Mime-Version'] = '1.0 (Apple Message framework v1278)'
        new_message['X-Apple-Mail-Remote-Attachments'] = 'YES'
        new_message['Content-Transfer-Encoding'] = '7bit'
        new_message['X-Uniform-Type-Identifier'] = 'com.apple.mail-note'
        new_message['X-Apple-Base-Url'] = "x-msg://%d/" % (int(ids[-1])+1)
        new_message['Date'] = rfc822.formatdate(time.time())
        new_message.set_payload(note_contents)

        self.connect()
        self._conn.append('Notes', '', imaplib.Time2Internaldate(
            time.time()), str(new_message))
                

def main():
    if len(sys.argv) < 2:
        print "You must supply the hostname of your mail server"
        exit(0)

    mail_from = None
    username = None

    servername = sys.argv[1]        
    homedir = expanduser("~")
    if os.path.exists("%s/.mapplenotes" % homedir):
        Config = ConfigParser.ConfigParser() 
        Config.read("%s/.mapplenotes" % homedir)
        if servername in Config.sections():
            username = Config.get(servername, "username")
            mail_from = Config.get(servername, "mail_from")

    if not username:
        sys.stdout.write("Username: ")
        username = raw_input()

    if not mail_from:
        sys.stdout.write("From: ")
        mail_from = raw_input()

    nm = NoteManager(servername, username, mail_from)        

    valid_cred = False
    while not valid_cred:
        password = getpass.getpass("Password: ")
        nm.set_password(password)
        try:
            nm.connect()
        except imaplib.IMAP4.error, iex:
            if str(iex) != "[AUTHENTICATIONFAILED] Authentication failed.":
                print "An IMAP exception occured: %s" % str(iex)
                tb = traceback.format_exc()
                print tb
                exit(1)
            else:
                print "Authentication Failed!"
                continue
        valid_cred = True
        
    nm.cmdloop()

if __name__ == "__main__":
    main()
