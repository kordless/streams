from pyotp.otp import OTP
import datetime
import time
import urllib


class TOTP(OTP):
    def __init__(self, *args, **kwargs):
        """
        @option options [Integer] interval (30) the time interval in seconds
            for OTP This defaults to 30 which is standard.
        """
        self.interval = kwargs.pop('interval', 30)
        super(TOTP, self).__init__(*args, **kwargs)

    def at(self, for_time):
        """
        Accepts either a Unix timestamp integer or a Time object.
        Time objects will be adjusted to UTC automatically
        @param [Time/Integer] time the time to generate an OTP for
        """
        if not isinstance(for_time, datetime.datetime):
            for_time = datetime.datetime.fromtimestamp(int(for_time))

        return self.generate_otp(self.timecode(for_time))

    def now(self):
        """
        Generate the current time OTP
        @return [Integer] the OTP as an integer
        """
        return self.generate_otp(self.timecode(datetime.datetime.now()))

    def verify(self, otp, for_time=None):
        """
        Verifies the OTP passed in against the current time OTP
        @param [String/Integer] otp the OTP to check against
        """
        if for_time is None:
            for_time = datetime.datetime.now()
        return unicode(otp) == unicode(self.at(for_time)).zfill(6)

    def provisioning_uri(self, name):
        """
        Returns the provisioning URI for the OTP
        This can then be encoded in a QR Code and used
        to provision the Google Authenticator app
        @param [String] name of the account
        @return [String] provisioning uri
        """
        return 'otpauth://totp/%(name)s?secret=%(secret)s' % {
            'name': urllib.quote(name, safe='@'),
            'secret': self.secret,
        }

    def timecode(self, for_time):
        i = time.mktime(for_time.timetuple())
        return int(i / self.interval)
