from datetime import datetime, timedelta, timezone, date
from typing import Dict, List, Optional, Tuple
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Query, HTTPException, Header, Path
from pydantic import computed_field, Field, validator
from typing_extensions import Annotated

from .. import models

from ..utils import fetch_openvpn_config
from ..common.routers import BaseModel
from ..common.dependencies import get_settings
from ..dependencies import get_postgresql_session


log = logging.getLogger(__name__)

router = APIRouter()


class VPNConfig(BaseModel):
    provider: str
    protocol: str
    config: Dict[str, str]
    date_updated: str


def update_vpn_config(db: Session, provider_name: str):
    vpn_cert = fetch_openvpn_config()

    try:
        vpn_config = (
            db.query(models.OONIProbeVPNConfig)
            .filter(
                models.OONIProbeVPNConfig.provider == provider_name,
            )
            .one()
        )
        vpn_config.protocol = "openvpn"
        vpn_config.openvpn_ca = vpn_cert["ca"]
        vpn_config.openvpn_cert = vpn_cert["cert"]
        vpn_config.openvpn_key = vpn_cert["key"]
        db.commit()

    except sa.orm.exc.NoResultFound:
        vpn_config = models.OONIProbeVPNConfig(
            provider=provider_name,
            date_updated=datetime.now(timezone.utc),
            date_created=datetime.now(timezone.utc),
            protocol="openvpn",
            openvpn_ca=vpn_cert["ca"],
            openvpn_cert=vpn_cert["cert"],
            openvpn_key=vpn_cert["key"],
        )
        db.add(vpn_config)
        db.commit()

    return vpn_config


def get_or_update_riseup_vpn_config(db: Session, provider_name: str):
    vpn_config = (
        db.query(models.OONIProbeVPNConfig)
        .filter(
            models.OONIProbeVPNConfig.provider == provider_name,
            models.OONIProbeVPNConfig.date_updated
            > datetime.now(timezone.utc) - timedelta(days=7),
        )
        .first()
    )
    if vpn_config is None:
        return update_vpn_config(db, provider_name)
    return vpn_config


@router.get("/v2/ooniprobe/vpn-config/{provider_name}", tags=["ooniprobe"])
def list_vpn_configs(
    provider_name: str,
    db=Depends(get_postgresql_session),
    settings=Depends(get_settings),
) -> VPNConfig:
    """List OONIRun descriptors"""
    log.debug("list oonirun")

    if provider_name != "riseupvpn":
        raise HTTPException(status_code=404, detail="provider not found")

    vpn_config = get_or_update_riseup_vpn_config(db, provider_name)
    return VPNConfig(
        provider=provider_name,
        protocol="openvpn",
        config={
            "cert": vpn_config.openvpn_cert,
            "ca": vpn_config.openvpn_ca,
            "key": vpn_config.openvpn_key,
        },
        date_updated=vpn_config.date_updated.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    )