# tests/test_domain_specs.py
"""
Invariants over the domains this repository actually ships.

Everything else in the suite uses fixture domains. This module loads the real
`config/domains.yaml` and the real `ITEnergyCommunityDomain`, `ITParticipantDomain`
and `ITGridDomain`, and holds them to the rules that are otherwise only discovered
at startup — or, worse, in production:

* a declared domain must be importable and expose a module-level `domain` instance;
* a fetcher must name a client that `config/clients.yaml` defines;
* a caller-supplied scalar must never be interpolated into query *structure*
  (`.agents/knowledge/query-templates-are-two-phase.md`).

No external service is contacted: nothing here executes a query.
"""
from __future__ import annotations

import re

import pytest

from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.domain.config import load_domains_config
from celine.dt.core.loader import import_attr, load_yaml_files

DOMAINS_CONFIG = ["config/domains.yaml"]
CLIENTS_CONFIG = ["config/clients.yaml"]


def _declared_domains() -> list[DTDomain]:
    cfg = load_domains_config(DOMAINS_CONFIG)
    domains = []
    for spec in cfg.domains:
        if not spec.enabled:
            continue
        domains.append(import_attr(spec.import_path))
    return domains


def _configured_clients() -> set[str]:
    """Client names from YAML, without constructing any of them.

    `load_and_register_clients` instantiates each class and needs a token provider;
    the names are all this module needs.
    """
    names: set[str] = set()
    for data in load_yaml_files(CLIENTS_CONFIG):
        names.update(data.get("clients", {}))
    return names


def _all_specs() -> list[tuple[DTDomain, ValueFetcherSpec]]:
    return [(d, s) for d in _declared_domains() for s in d.get_value_specs()]


def _spec_ids() -> list[str]:
    return [f"{d.name}.{s.id}" for d, s in _all_specs()]


# -- declaration ----------------------------------------------------------------


class TestDeclaredDomains:
    # @verifies REQ-1004
    def test_every_declared_domain_imports(self):
        """A typo in the import path is a startup crash, and nothing else catches it."""
        assert _declared_domains()

    # @verifies REQ-1004
    def test_import_target_is_an_instance_not_a_class(self):
        """The loader looks for a module-level `domain = MyDomain()`.

        A domain constructed inside a function — or left as a class — is silently
        not found. See `.agents/playbooks/extending-a-domain.md`.
        """
        for domain in _declared_domains():
            assert isinstance(domain, DTDomain), f"{domain!r} is not a DTDomain instance"

    # @verifies REQ-1003
    def test_identity_attributes_are_set(self):
        for domain in _declared_domains():
            assert domain.name
            assert domain.domain_type
            assert domain.route_prefix.startswith("/")
            assert not domain.route_prefix.endswith("/")
            assert domain.entity_id_param

    # @verifies REQ-1002
    def test_route_prefixes_are_unique(self):
        prefixes = [d.route_prefix for d in _declared_domains()]
        assert len(prefixes) == len(set(prefixes))

    # @verifies REQ-1001
    def test_domain_names_are_unique(self):
        names = [d.name for d in _declared_domains()]
        assert len(names) == len(set(names))


# -- fetchers -------------------------------------------------------------------


class TestFetcherSpecs:
    def test_there_are_fetchers_to_check(self):
        assert _all_specs()

    # @verifies REQ-1100
    def test_namespaced_ids_are_unique(self):
        ids = _spec_ids()
        assert len(ids) == len(set(ids))

    # @verifies REQ-1101
    def test_every_fetcher_names_a_configured_client(self):
        """`main._register_domain_values` raises at startup on an unknown client.

        Catching it here means a mistyped client name fails in the suite rather than
        on the first deploy.
        """
        configured = _configured_clients()
        for domain, spec in _all_specs():
            assert (
                spec.client in configured
            ), f"{domain.name}.{spec.id} references unknown client '{spec.client}'"

    def test_limits_are_positive(self):
        for domain, spec in _all_specs():
            assert spec.limit > 0, f"{domain.name}.{spec.id}"
            assert spec.offset >= 0, f"{domain.name}.{spec.id}"

    def test_payload_schemas_are_objects(self):
        for domain, spec in _all_specs():
            if spec.payload_schema is None:
                continue
            assert (
                spec.payload_schema.get("type") == "object"
            ), f"{domain.name}.{spec.id} payload_schema is not an object schema"


# -- the two-phase rule ---------------------------------------------------------

# `{{ name }}` or `{{ name | filter }}` — captures the root identifier and the
# first filter applied to it, if any.
INTERPOLATION = re.compile(r"\{\{\s*([A-Za-z_][\w]*)\s*(?:\.[\w.]+)?\s*(\|\s*(\w+))?")

SAFE_FILTERS = {"sql_list", "sql_quote"}


class TestNoCallerDataInQueryStructure:
    """A caller-supplied scalar must reach the query as a bind parameter.

    Interpolating one with `{{ }}` puts request data into the statement's structure.
    `entity.*` is exempt: it comes from `resolve_entity`, not from the request body.
    The two SQL filters are exempt because escaping is what they do.

    This is the rule `.agents/knowledge/query-templates-are-two-phase.md` states, held
    against every shipped fetcher rather than against a fixture.
    """

    # @verifies REQ-1211
    def test_payload_properties_are_not_interpolated_unsafely(self):
        offenders: list[str] = []
        for domain, spec in _all_specs():
            if not spec.query or not spec.payload_schema:
                continue
            properties = set(spec.payload_schema.get("properties", {}))
            for match in INTERPOLATION.finditer(spec.query):
                root, _, filter_name = match.groups()
                if root not in properties:
                    continue
                if filter_name in SAFE_FILTERS:
                    continue
                offenders.append(
                    f"{domain.name}.{spec.id}: '{{{{ {root} }}}}' interpolates a "
                    f"payload property into query structure"
                )
        assert not offenders, "\n".join(offenders)

    # @verifies REQ-1213
    def test_bind_parameters_are_declared_in_the_payload_schema(self):
        """Every `:param` must be something the caller can actually supply.

        An undeclared bind parameter raises `Bind parameter ':x' not provided` at
        request time — a 500 for a fetcher that can never succeed. Casts (`::date`)
        are excluded by the same negative lookbehind the renderer uses.
        """
        bind = re.compile(r"(?<!:):(\w+)")
        offenders: list[str] = []
        for domain, spec in _all_specs():
            if not spec.query:
                continue
            declared = set((spec.payload_schema or {}).get("properties", {}))
            for name in set(bind.findall(spec.query)):
                if name not in declared:
                    offenders.append(
                        f"{domain.name}.{spec.id}: ':{name}' is not declared in "
                        f"payload_schema"
                    )
        assert not offenders, "\n".join(offenders)


def _sample_value(schema: dict) -> object:
    """A value satisfying `schema`'s declared type.

    Only the type matters: rendering does not validate, so patterns and enums are
    irrelevant here. What matters is that a list stays a list — `sql_list` rejects
    anything else, and that rejection is a fetcher-level 500.
    """
    match schema.get("type"):
        case "array":
            return [_sample_value(schema.get("items", {"type": "string"}))]
        case "integer":
            return 1
        case "number":
            return 1.5
        case "boolean":
            return True
        case "object":
            return {}
        case _:
            return "x"


def _payload_for(spec: ValueFetcherSpec, *, full: bool) -> dict:
    """Build a payload for `spec`.

    `full=False` supplies only what the caller must: required properties and any
    declared defaults. `full=True` supplies every declared property. The two
    together take both branches of each `{% if optional %}` in the template.
    """
    schema = spec.payload_schema or {}
    properties: dict = schema.get("properties", {})
    required = set(schema.get("required", []))

    params: dict = {}
    for name, prop in properties.items():
        if "default" in prop:
            params[name] = prop["default"]
        elif full or name in required:
            params[name] = _sample_value(prop)

    # A bind parameter the schema never declared still has to resolve, or rendering
    # raises. `test_bind_parameters_are_declared_in_the_payload_schema` is what keeps
    # this from silently papering over one.
    for name in re.findall(r"(?<!:):(\w+)", spec.query or ""):
        params.setdefault(name, "x")

    return params


class TestRenderability:
    """Every shipped query must render under a valid payload.

    A template that renders only for some payloads is a fetcher that 500s for the
    rest, and nothing before this point would notice — the query is a string until
    the moment a request arrives.
    """

    @pytest.mark.parametrize("full", [False, True], ids=["minimal", "full"])
    @pytest.mark.parametrize("spec_id", _spec_ids())
    # @verifies REQ-1250 REQ-1251
    def test_query_renders(self, spec_id: str, full: bool):
        from celine.dt.contracts.entity import EntityInfo
        from celine.dt.core.values.template import render_query

        domain, spec = next(
            (d, s) for d, s in _all_specs() if f"{d.name}.{s.id}" == spec_id
        )
        if not spec.query:
            pytest.skip(f"{spec_id} declares no query")

        entity = EntityInfo(id="test-entity", domain_name=domain.name, metadata={})
        rendered = render_query(
            spec.query, entity=entity, params=_payload_for(spec, full=full)
        )

        assert rendered.strip()
        # Nothing may survive the two phases unrendered.
        assert "{{" not in rendered
        assert "{%" not in rendered
        assert re.search(r"(?<!:):\w+", rendered) is None
