# -*- coding: utf-8 -*-
"""Authentication utilities."""
"""
  Kontalk XMPP server
  Copyright (C) 2011 Kontalk Devteam <devteam@kontalk.org>

 This program is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""


from zope.interface import implements

from twisted.web import iweb
from twisted.cred import credentials, checkers, error, portal
from twisted.python import failure
from twisted.internet import defer
from twisted.words.protocols.jabber import jid, sasl

import xmlstream2, log, util, tls


class OpenPGPKontalkCredentials(tls.OpenPGPCredentials):
    """Kontalk-enhanced OpenPGP credentials."""

    def __init__(self, cert, key, keyring, portal):
        tls.OpenPGPCredentials.__init__(self, cert, key, keyring)
        self.portal = portal

    def verify_callback(self, peer_cert, preverify_status=None):
        print peer_cert, preverify_status
        tls.OpenPGPCredentials.verify_callback(self, peer_cert, preverify_status)
        self.portal.login(KontalkCertificate(peer_cert), None, xmlstream2.IXMPPUser)


class IKontalkCertificate(credentials.ICredentials):

    def check(fingerprint, keyring):
        pass


class KontalkCertificate(object):
    implements(IKontalkCertificate)

    def __init__(self, cert):
        self.cert = cert

    def check(self, fingerprint, keyring):
        uid = self.cert.uid(0)
        return jid.JID(uid.email)


class IKontalkToken(credentials.ICredentials):

    def check(fingerprint, keyring):
        pass


class KontalkToken(object):
    implements(IKontalkToken)

    def __init__(self, token, decode_b64=False):
        self.token = token
        self.decode_b64 = decode_b64

    def check(self, fingerprint, keyring):
        try:
            if self.decode_b64:
                data = sasl.fromBase64(self.token)
            else:
                data = self.token

            return keyring.check_token(data)
        except:
            # TODO logging or throw exception back
            import traceback
            traceback.print_exc()
            log.debug("token verification failed!")


class AuthKontalkChecker(object):
    implements(checkers.ICredentialsChecker)

    credentialInterfaces = IKontalkToken, IKontalkCertificate

    def __init__(self, fingerprint, keyring):
        self.fingerprint = str(fingerprint)
        self.keyring = keyring

    def _cbTokenValid(self, userid):
        if userid:
            return userid
        else:
            return failure.Failure(error.UnauthorizedLogin())

    def requestAvatarId(self, credentials):
        return defer.maybeDeferred(
            credentials.check, self.fingerprint, self.keyring).addCallback(
            self._cbTokenValid)


class AuthKontalkTokenFactory(object):
    implements(iweb.ICredentialFactory)

    scheme = 'kontalktoken'

    def __init__(self, fingerprint, keyring):
        self.fingerprint = fingerprint
        self.keyring = keyring

    def getChallenge(self, request):
        return {}

    def decode(self, response, request):
        key, token = response.split('=', 1)
        if key == 'auth':
            return KontalkToken(token, True)

        raise error.LoginFailed('Invalid token')


class SASLRealm:
    """
    A twisted.cred Realm for XMPP/SASL authentication

    You can subclass this and override the buildAvatar function to return an
    object that implements the IXMPPUser interface.
    """

    implements(portal.IRealm)

    def __init__(self, name):
        """ @param name: a string identifying the realm
        """
        self.name = name

    def requestAvatar(self, avatarId, mind, *interfaces):
        if xmlstream2.IXMPPUser in interfaces:
            avatar = self.buildAvatar(avatarId)
            return xmlstream2.IXMPPUser, avatar, avatar.logout
        else:
            raise NotImplementedError("Only IXMPPUser interface is supported by this realm")

    def buildAvatar(self, avatarId):
        # The hostname will be overwritten by the SASLReceivingInitializer
        # We put in example.com to keep the JID constructor from complaining
        if isinstance(avatarId, jid.JID):
            _jid = avatarId
            # generate random resource
            _jid.resource = util.rand_str(8, util.CHARSBOX_AZN_UPPERCASE)
        else:
            userid, resource = util.split_userid(avatarId)
            _jid = jid.JID(tuple=(userid, "example.com", resource))
        return xmlstream2.XMPPUser(_jid)
