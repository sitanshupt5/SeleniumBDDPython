# utilities/allure_helpers.py
import allure
from allure_commons.types import AttachmentType


def attach_text(name: str, text: str) -> None:
    """
    Attach plain text to the Allure report.

    :param name: Display name of the attachment as it will appear in the report.
    :param text: Text content to attach. If falsy, an empty string is attached.
    :returns: None
    """
    allure.attach(text or "", name=name, attachment_type=AttachmentType.TEXT)


def attach_png(name: str, png_bytes: bytes) -> None:
    """
    Attach a PNG image (as raw bytes) to the Allure report.

    :param name: Display name of the image attachment.
    :param png_bytes: PNG image data as bytes. If falsy, nothing is attached.
    :returns: None
    """
    if png_bytes:
        allure.attach(png_bytes, name=name, attachment_type=AttachmentType.PNG)
