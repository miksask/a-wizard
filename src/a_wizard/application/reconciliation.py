"""Reconcile project stage freshness against signatures and digests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from a_wizard.adapters.persistence.store import FsArtifactStore, ensure_under
from a_wizard.domain.freshness import (
    content_fingerprint,
    invalidate_from_stage,
    mark_stale_downstream,
    resolve_digest_map,
    stage_contracts,
)
from a_wizard.domain.models import Project, StageStatus


@dataclass
class ReconcileResult:
    invalidated: list[str]
    changed: bool
    reasons: dict[str, str]


def _artifact_ok(
    project_dir: Path,
    store: FsArtifactStore,
    rel: str,
    expected_digest: str | None,
) -> tuple[bool, str | None]:
    path = ensure_under(project_dir, rel)
    if not path.is_file():
        return False, f"missing:{rel}"
    if expected_digest:
        actual = store.digest(project_dir, rel)
        if actual != expected_digest:
            return False, f"digest_mismatch:{rel}"
    return True, None


def refresh_source_fingerprint(project: Project) -> bool:
    """Update content_fingerprint from source path when readable. Returns True if changed."""
    src = project.source.get("path")
    if not src:
        return False
    path = Path(src)
    if not path.is_file():
        return False
    try:
        fp = content_fingerprint(path)
    except OSError:
        return False
    if project.source.get("content_fingerprint") == fp:
        return False
    project.source["content_fingerprint"] = fp
    return True


def apply_adapter_identity(
    project: Project,
    *,
    asr_id: str | None,
    diar_id: str | None,
    media_id: str | None = None,
) -> list[str]:
    """Update project.adapters and stale dependents when identities change."""
    invalidated: list[str] = []
    adapters = project.adapters or {}
    if asr_id and adapters.get("asr") != asr_id:
        adapters["asr"] = asr_id
        invalidated.extend(mark_stale_downstream(project, "asr_adapter"))
    if diar_id and adapters.get("diarization") != diar_id:
        adapters["diarization"] = diar_id
        invalidated.extend(mark_stale_downstream(project, "diar_adapter"))
    if media_id and adapters.get("media") != media_id:
        adapters["media"] = media_id
        invalidated.extend(mark_stale_downstream(project, "extract"))
    project.adapters = adapters
    return invalidated


def reconcile_project(
    project_dir: Path,
    project: Project,
    store: FsArtifactStore | None = None,
    *,
    refresh_fingerprint: bool = True,
) -> ReconcileResult:
    """Verify succeeded stages; mark broken stages and dependents stale.

    Does not persist — caller saves when ``changed`` is True.
    """
    store = store or FsArtifactStore()
    invalidated: list[str] = []
    reasons: dict[str, str] = {}
    changed = False

    if refresh_fingerprint and refresh_source_fingerprint(project):
        changed = True
        if project.stage("extract").status == StageStatus.SUCCEEDED:
            keys = invalidate_from_stage(project, "extract")
            invalidated.extend(keys)
            reasons["extract"] = "source_fingerprint_changed"
            return ReconcileResult(invalidated=invalidated, changed=True, reasons=reasons)

    for contract in stage_contracts(project):
        rec = project.stage(contract.key)
        if rec.status == StageStatus.RUNNING:
            keys = invalidate_from_stage(project, contract.key)
            if project.stage(contract.key).status != StageStatus.STALE:
                project.stage(contract.key).status = StageStatus.STALE
                keys = [contract.key, *keys]
            invalidated.extend(keys)
            reasons[contract.key] = "interrupted_running"
            changed = True
            break

        if rec.status != StageStatus.SUCCEEDED:
            continue

        expected_sig = contract.signature_fn(project)
        if rec.signature and rec.signature != expected_sig:
            keys = invalidate_from_stage(project, contract.key)
            invalidated.extend(keys)
            reasons[contract.key] = "signature_mismatch"
            changed = True
            break

        path_digests = resolve_digest_map(contract, rec.output_digests)
        bad: str | None = None
        for rel in contract.required_outputs:
            ok, why = _artifact_ok(project_dir, store, rel, path_digests.get(rel))
            if not ok:
                bad = why
                break
        if bad:
            keys = invalidate_from_stage(project, contract.key)
            invalidated.extend(keys)
            reasons[contract.key] = bad
            changed = True
            break

        # Backfill missing signature when digests already prove freshness.
        if not rec.signature:
            rec.signature = expected_sig
            changed = True

    seen: set[str] = set()
    uniq: list[str] = []
    for k in invalidated:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    return ReconcileResult(invalidated=uniq, changed=changed, reasons=reasons)
