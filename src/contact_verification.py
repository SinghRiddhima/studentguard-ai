"""Send and check contact verification codes through Twilio Verify."""
import base64
import json
import os
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LABELS = {"email": "Email address", "sms": "Phone number"}


def normalise_contact(channel, value):
    value = value.strip()
    if channel == "email":
        if len(value) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", value):
            raise ValueError("Enter a valid email address.")
        return value.lower()
    if channel == "sms":
        value = value.translate(str.maketrans("", "", " ()-"))
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", value):
            raise ValueError("Enter a phone number with its country code, such as +91 followed by the number.")
        return value
    raise ValueError("Unknown contact method.")


class VerificationError(ValueError):
    """A safe error message for the person requesting verification."""


@dataclass(frozen=True)
class VerifyService:
    service_sid: str
    api_key: str
    api_secret: str

    @classmethod
    def configured(cls):
        names = ("TWILIO_VERIFY_SERVICE_SID", "TWILIO_VERIFY_API_KEY", "TWILIO_VERIFY_API_SECRET")
        values = tuple(os.environ.get(name, "").strip() for name in names)
        if not any(values):
            return None
        if not all(values) or not re.fullmatch(r"VA[0-9a-fA-F]{32}", values[0]):
            raise VerificationError("Contact verification is temporarily unavailable. Check the service configuration.")
        return cls(*values)

    def _post(self, resource, **fields):
        token = base64.b64encode(f"{self.api_key}:{self.api_secret}".encode()).decode()
        request = Request(
            f"https://verify.twilio.com/v2/Services/{self.service_sid}/{resource}",
            data=urlencode(fields).encode(),
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(request, timeout=8) as response:
                return json.load(response)
        except HTTPError as exc:
            if resource == "VerificationCheck" and exc.code in {400, 404}:
                raise VerificationError("The code is incorrect or expired. Try again or request a new code.") from exc
            if exc.code == 429:
                raise VerificationError("Too many verification attempts. Please wait before trying again.") from exc
            raise VerificationError("The verification service could not complete this request. Try again later.") from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise VerificationError("The verification service is temporarily unavailable. Try again later.") from exc

    def send(self, channel, destination):
        result = self._post("Verifications", To=normalise_contact(channel, destination), Channel=channel)
        if result.get("status") != "pending" or not result.get("sid"):
            raise VerificationError("The verification service could not send a code. Please try again.")
        return result["sid"]

    def check(self, channel, destination, sid, code):
        if not re.fullmatch(r"[0-9]{4,10}", code.strip()):
            raise VerificationError("Enter the numeric code you received.")
        destination = normalise_contact(channel, destination)
        result = self._post("VerificationCheck", VerificationSid=sid, Code=code.strip())
        if (result.get("status") != "approved" or result.get("sid") != sid
                or (result.get("to") or "").lower() != destination):
            raise VerificationError("The code is incorrect or expired. Try again or request a new code.")
