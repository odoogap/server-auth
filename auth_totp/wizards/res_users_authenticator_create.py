# Copyright 2016-2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

import logging

from werkzeug import urls

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)
try:
    import pyotp
except ImportError:
    _logger.debug(
        "Could not import PyOTP. Please make sure this library is available in"
        " your environment."
    )


class ResUsersAuthenticatorCreate(models.TransientModel):
    _name = "res.users.authenticator.create"
    _description = "MFA App/Device Creation Wizard"

    name = fields.Char(
        string="Authentication App/Device Name",
        help="A name that will help you remember this authentication" " app/device",
        required=True,
    )
    secret_key = fields.Char(
        string="Secret Code", default=lambda s: pyotp.random_base32(), required=True,
    )
    qr_code_tag = fields.Html(
        compute="_compute_qr_code_tag",
        string="QR Code",
        help="Scan this image with your authentication app to add your" " account",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda s: s._default_user_id(),
        required=True,
        string="Associated User",
        help="This is the user whose account the new authentication app/device"
        " will be tied to",
        readonly=True,
        ondelete="cascade",
    )
    confirmation_code = fields.Char(
        string="Confirmation Code",
        help="Enter the latest six digit code generated by your authentication" " app",
        required=True,
    )

    @api.model
    def _default_user_id(self):
        user_id = self.env.context.get("uid")
        return self.env["res.users"].browse(user_id)

    @api.multi
    @api.depends(
        "secret_key", "user_id.display_name", "user_id.company_id.display_name",
    )
    def _compute_qr_code_tag(self):
        for record in self:
            if not record.user_id:
                continue

            totp = pyotp.TOTP(record.secret_key)
            provisioning_uri = totp.provisioning_uri(
                record.user_id.display_name.encode("utf-8"),
                issuer_name=record.user_id.company_id.display_name,
            )
            provisioning_uri = urls.url_quote(provisioning_uri)

            qr_width = qr_height = 300
            tag_base = '<img src="/report/barcode/?type=QR&amp;'
            tag_params = 'value=%s&amp;width=%s&amp;height=%s">' % (
                provisioning_uri,
                qr_width,
                qr_height,
            )
            record.qr_code_tag = tag_base + tag_params

    @api.multi
    def action_create(self):
        self.ensure_one()
        self._perform_validations()
        self._create_authenticator()

        action_data = self.env.ref("base.action_res_users_my").read()[0]
        action_data.update({"res_id": self.user_id.id})
        return action_data

    @api.multi
    def _perform_validations(self):
        totp = pyotp.TOTP(self.secret_key)
        if not totp.verify(self.confirmation_code):
            raise ValidationError(
                _(
                    "Your confirmation code is not correct. Please try again,"
                    " making sure that your MFA device is set to the correct time"
                    " and that you have entered the most recent code generated by"
                    " your authentication app."
                )
            )

    @api.multi
    def _create_authenticator(self):
        self.env["res.users.authenticator"].create(
            {
                "name": self.name,
                "secret_key": self.secret_key,
                "user_id": self.user_id.id,
            }
        )
