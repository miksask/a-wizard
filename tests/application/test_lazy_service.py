"""Metadata-only service does not resolve heavy adapters."""

from __future__ import annotations

from a_wizard.application.service import ServiceConfig, WizardService


def test_metadata_only_does_not_resolve_adapters():
    cfg = ServiceConfig(metadata_only=True, asr_adapter="auto", diar_adapter="auto")
    svc = WizardService(config=cfg)
    assert svc._asr_resolved is False
    assert svc._diar_resolved is False
    # Accessing reconcile path without adapters
    assert svc.config.metadata_only is True


def test_processing_service_resolves_mock():
    svc = WizardService(config=ServiceConfig(use_mock_engines=True, metadata_only=False))
    assert svc.asr.adapter_id == "mock-asr"
    assert svc.diar.adapter_id == "mock-diar"
