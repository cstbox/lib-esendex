# -*- coding: utf-8 -*-

import textwrap
from collections import namedtuple
from xml.etree import ElementTree as ET
import re

import arrow
import requests

__author__ = 'Eric Pascual - CSTB (eric.pascual@cstb.fr)'

PHONE_NUMBER_REGEX = "^([0-9]{2} *){5}$"


class MessageStatus(namedtuple('MessageStatus', 'status updated_at')):
    """ Message statuses corresponding to the different steps, when they can be tracked.
    """
    __slots__ = ()
    SUBMITTED, SENT, DELIVERED, FAILED, ACKNOWLEDGED, EXPIRED, UNKNOWN = xrange(7)
    _names = (
        'SUBMITTED', 'SENT', 'DELIVERED', 'FAILED', 'ACKNOWLEDGED', 'EXPIRED', 'UNKNOWN'
    )

    def __new__(cls, status, updated_at=None):
        if status not in (cls.SUBMITTED, cls.SENT, cls.DELIVERED, cls.FAILED, cls.ACKNOWLEDGED, cls.EXPIRED, cls.UNKNOWN):
            raise ValueError(status)
        return super(cls, MessageStatus).__new__(cls, status, updated_at)

    def __str__(self):
        return "%s (%s)" % (self._names[self.status], self.updated_at.isoformat())

    @classmethod
    def status_to_string(cls, status):
        return cls._names[status]


class EsendexService(object):
    """ Notification service for sending phone vocal messages or SMS using the Esendex commercial platform.
    """

    MSG_VOICE = 0
    MSG_SMS = 1

    HOST = "https://api.esendex.com"
    SEND_MESSAGE_URL = "/v1.0/messagedispatcher"
    SEND_MESSAGE_REQUEST = textwrap.dedent("""
        <?xml version='1.0' encoding='UTF-8'?>
        <messages>
            <accountreference>%(account)s</accountreference>
            <from>%(from)s</from>
            <message>
                <to>%(to)s</to>
                <type>%(msg_type)s</type>
                <body>%(message)s</body>
                <lang>fr-FR</lang>
                <retries>%(retries)d</retries>
            </message>
        </messages>
    """).strip('\n')
    MSG_STATUS_URL = "/v1.0/messageheaders/%s"
    NAMESPACE = "http://api.esendex.com/ns/"

    _inv_dict = {
        'submitted': MessageStatus.SUBMITTED,
        'sent': MessageStatus.SENT,
        'delivered': MessageStatus.DELIVERED,
        'failed': MessageStatus.FAILED,
        'failed authorisation': MessageStatus.FAILED,
        'acknowledged': MessageStatus.ACKNOWLEDGED,
        'expired': MessageStatus.EXPIRED
    }

    def __init__(self, account, login, password, sender,
                 time_zone=None,
                 retries=1,
                 simulate=False,
                 debug_host=None
                 ):
        """
         :param
        """
        if not all([account, login, password, sender]):
            raise ValueError('missing or empty mandatory parameter')

        self._account = account
        self._login = login
        self._password = password
        if re.match(PHONE_NUMBER_REGEX, sender):
            self._sender = sender
        else:
            raise ValueError('invalid sender phone number (%s)' % sender)

        self._tz = time_zone or 'Europe/Paris'
        self._retries = max(1, retries)

        self._simulate = simulate
        if debug_host:
            self.HOST = debug_host

    @classmethod
    def _fqtag(cls, tag):
        return "{%s}%s" % (cls.NAMESPACE, tag)

    def emit_message(self, recipient, message, message_type=MSG_VOICE):
        """ Emit a message to a recipient.

        The message can be sent as either a phone call (default) or a SMS (up to 140 chars).

        :param str recipient: the phone number of the recipient
        :param str message: the text of the message
        :param int message_type: the form of the message (`MSG_VOICE` or `MSG_SMS`, defaulted to `MSG_VOICE`)
        :raise ValueError: if wrong message type, or SMS text too long
        """
        if message_type not in (self.MSG_SMS, self.MSG_VOICE):
            raise ValueError("invalid message type (%s)" % message_type)
        if message_type == self.MSG_SMS and len(message) > 140:
            raise ValueError('SMS message cannot be more than 140 chars long')

        try:
            message = unicode(message, 'utf-8')
        except TypeError:
            # was already Unicode text
            pass

        request = self.SEND_MESSAGE_REQUEST % {
            'account': self._account,
            'from': self._sender,
            'to': recipient,
            'msg_type': ('Voice', 'SMS')[message_type],
            'message': unicode(message),
            'retries': self._retries
        }
        url = self.HOST + self.SEND_MESSAGE_URL
        if not self._simulate:
            response = requests.post(
                url,
                data=request.encode('utf-8'),
                headers={'Content-Type': 'application/xml; charset=utf-8'},
                auth=(self._login, self._password)
            )
            try:
                response.raise_for_status()

                root = ET.fromstring(response.content)
                message_id = root.find(self._fqtag('messageheader')).get('id')
                return message_id
            except requests.HTTPError as e:
                raise EsendexAPIError(e)

        else:
            print('[SIM] sending request :\n%s\n---' % request)
            print('to URL : ' + url)
            print('with auth : (%s, %s)' % (self._login, self._password))
            return "42"

    def get_message_status(self, message_id):
        """ Queries Esendex server for the status of a previously sent message.

        :param str message_id: the id of the message
        :return: a MessageStatus or None if not available
        :raise: ValueError if message id is not found
        """
        if not self._simulate:
            response = requests.get(
                self.HOST + (self.MSG_STATUS_URL % message_id),
                auth=(self._login, self._password)
            )
            if response.ok:
                root = ET.fromstring(response.content)
                status_str = root.findtext(self._fqtag('status'))
                status = self._inv_dict.get(status_str.lower(), MessageStatus.UNKNOWN)
                status_time = root.findtext(self._fqtag('laststatusat'))
                return MessageStatus(status, arrow.get(status_time).datetime)

            elif response.status_code == 404:
                raise ValueError('message not found (%s)' % message_id)

        else:
            return MessageStatus(MessageStatus.DELIVERED, arrow.now(tz=self._tz))


class EsendexAPIError(Exception):
    """ Dedicated exception for notification related actions
    """
