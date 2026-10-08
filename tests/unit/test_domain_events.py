"""TASK-001: the domain event envelope (`Event`, `StoredEvent`) and `EventType`.

Each test names the acceptance criterion it covers (AC1..AC17 in
docs/tasks/TASK-001-domain-event-model.md).
"""

import ast
import importlib.util
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid1, uuid4, uuid5

import pytest
from pydantic import ValidationError

from openfactory.domain.events import Event, EventType, StoredEvent

EVENT_TYPE_NAMES = [
    "SpecImported",
    "SpecValidated",
    "SpecApproved",
    "PlanCreated",
    "PlanApproved",
    "TaskStateChanged",
    "AgentRunStarted",
    "AgentRunFinished",
    "GateEvaluated",
    "CommitRecorded",
    "ImpactComputed",
]

ENVELOPE_FIELDS = {
    "event_id",
    "stream",
    "type",
    "payload",
    "actor",
    "causation_id",
    "created_at",
}

BASELINE_INSTANT = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
BASELINE_ISO = "2026-10-08T12:00:00Z"

NESTED_PAYLOAD = {
    "text": "hello",
    "integer": 3,
    "float": 1.5,
    "yes": True,
    "no": False,
    "nothing": None,
    "list": [1, "two", 3.0, False, None, [4, 5], {"k": "v"}],
    "object": {"inner": {"deeper": [{"deepest": None}]}},
}


def event_kwargs(**overrides):
    """Keyword arguments for a valid Event; `overrides` replace or add fields.

    `event_id` is required (AC3), so each call supplies a freshly generated one.
    """
    kwargs = {
        "event_id": uuid4(),
        "stream": "task:AUTH-002",
        "type": "TaskStateChanged",
        "payload": {"from": "ready", "to": "running"},
        "actor": "orchestrator",
        "created_at": BASELINE_INSTANT,
    }
    kwargs.update(overrides)
    return kwargs


def event_kwargs_without(field):
    kwargs = event_kwargs()
    del kwargs[field]
    return kwargs


# --- AC1: EventType holds exactly the 11 Phase 1 names ---------------------------------


def test_ac01_event_type_has_exactly_the_eleven_phase1_values():
    assert sorted(member.value for member in EventType) == sorted(EVENT_TYPE_NAMES)
    assert len(list(EventType)) == 11


@pytest.mark.parametrize("name", EVENT_TYPE_NAMES)
def test_ac01_event_type_contains_value(name):
    member = EventType(name)
    assert member.value == name
    assert isinstance(member, str)


@pytest.mark.parametrize("name", ["ApprovalGiven", "TaskInvalidated", "TaskStarted", ""])
def test_ac01_event_type_has_no_other_value(name):
    with pytest.raises(ValueError):
        EventType(name)


# --- AC2: Event exposes exactly the envelope columns, and no seq ------------------------


def test_ac02_event_fields_are_exactly_the_envelope_columns():
    assert set(Event.model_fields) == ENVELOPE_FIELDS


def test_ac02_event_has_no_seq_field():
    assert "seq" not in Event.model_fields
    assert not hasattr(Event(**event_kwargs()), "seq")


def test_ac02_event_exposes_the_values_it_was_built_with():
    event_id = uuid4()
    event = Event(**event_kwargs(event_id=event_id))
    assert event.event_id == event_id
    assert event.stream == "task:AUTH-002"
    assert event.type == EventType.TaskStateChanged
    assert event.payload == {"from": "ready", "to": "running"}
    assert event.actor == "orchestrator"
    assert event.causation_id is None
    assert event.created_at == BASELINE_INSTANT


# --- AC3: NOT NULL columns are required -------------------------------------------------


NOT_NULL_FIELDS = ["event_id", "stream", "type", "payload", "actor", "created_at"]


@pytest.mark.parametrize("field", NOT_NULL_FIELDS)
def test_ac03_event_requires_field(field):
    with pytest.raises(ValidationError) as excinfo:
        Event(**event_kwargs_without(field))
    assert [error["loc"] for error in excinfo.value.errors()] == [(field,)]
    assert excinfo.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("field", NOT_NULL_FIELDS)
def test_ac03_stored_event_requires_field(field):
    with pytest.raises(ValidationError) as excinfo:
        StoredEvent(**event_kwargs_without(field), seq=1)
    assert [error["loc"] for error in excinfo.value.errors()] == [(field,)]
    assert excinfo.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("field", NOT_NULL_FIELDS)
def test_ac03_event_rejects_none_for_not_null_field(field):
    with pytest.raises(ValidationError):
        Event(**event_kwargs(**{field: None}))


# --- AC4: causation_id is nullable -----------------------------------------------------


def test_ac04_causation_id_defaults_to_none_when_omitted():
    kwargs = event_kwargs()
    assert "causation_id" not in kwargs
    assert Event(**kwargs).causation_id is None


def test_ac04_causation_id_accepts_explicit_none():
    assert Event(**event_kwargs(causation_id=None)).causation_id is None


def test_ac04_causation_id_can_reference_another_event():
    cause = Event(**event_kwargs())
    effect = Event(**event_kwargs(causation_id=str(cause.event_id)))
    assert effect.causation_id == cause.event_id
    assert effect.event_id != cause.event_id


# --- AC5: any valid UUID is accepted as event_id ----------------------------------------

UUIDS_BY_VERSION = {
    "uuid1": uuid1(),
    "uuid4": uuid4(),
    "uuid5": uuid5(UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), "openfactory"),
}


@pytest.mark.parametrize("value", UUIDS_BY_VERSION.values(), ids=UUIDS_BY_VERSION.keys())
def test_ac05_event_id_accepts_uuid_object_of_any_version(value):
    event = Event(**event_kwargs(event_id=value))
    assert event.event_id == value
    assert event.event_id.version == value.version


@pytest.mark.parametrize("value", UUIDS_BY_VERSION.values(), ids=UUIDS_BY_VERSION.keys())
def test_ac05_event_id_accepts_uuid_string_of_any_version(value):
    event = Event(**event_kwargs(event_id=str(value)))
    assert isinstance(event.event_id, UUID)
    assert event.event_id == value


@pytest.mark.parametrize(
    "value",
    ["not-a-uuid", "", "12345", "6ba7b810-9dad-11d1-80b4-00c04fd430cZ"],
    ids=["not-a-uuid", "empty", "digits", "bad-hex-digit"],
)
def test_ac05_event_id_rejects_non_uuid_string(value):
    with pytest.raises(ValidationError):
        Event(**event_kwargs(event_id=value))


# --- AC6: event_id has no default; Event.new generates a UUID4 and a UTC created_at -----


def new_kwargs(**overrides):
    """Keyword arguments for a valid `Event.new` call; `overrides` replace or add."""
    kwargs = {
        "stream": "task:AUTH-002",
        "type": "TaskStateChanged",
        "payload": {"from": "ready", "to": "running"},
        "actor": "orchestrator",
    }
    kwargs.update(overrides)
    return kwargs


def test_ac06_event_id_has_no_default():
    assert Event.model_fields["event_id"].is_required()
    assert StoredEvent.model_fields["event_id"].is_required()


def test_ac06_new_returns_an_event_with_the_given_values():
    event = Event.new(**new_kwargs())
    assert type(event) is Event
    assert event.stream == "task:AUTH-002"
    assert event.type is EventType.TaskStateChanged
    assert event.payload == {"from": "ready", "to": "running"}
    assert event.actor == "orchestrator"


def test_ac06_new_takes_keyword_arguments_only():
    with pytest.raises(TypeError):
        Event.new("task:AUTH-002", "TaskStateChanged", {"from": "ready"}, "orchestrator")


def test_ac06_new_rejects_a_single_positional_argument():
    kwargs = new_kwargs()
    stream = kwargs.pop("stream")
    with pytest.raises(TypeError):
        Event.new(stream, **kwargs)


def test_ac06_new_generates_a_uuid4_event_id():
    event = Event.new(**new_kwargs())
    assert isinstance(event.event_id, UUID)
    assert event.event_id.version == 4


def test_ac06_new_generates_distinct_event_ids():
    first = Event.new(**new_kwargs())
    second = Event.new(**new_kwargs())
    assert first.event_id != second.event_id


def test_ac06_new_sets_created_at_to_the_current_utc_time():
    before = datetime.now(UTC)
    event = Event.new(**new_kwargs())
    after = datetime.now(UTC)
    assert isinstance(event.created_at, datetime)
    assert event.created_at.tzinfo is not None
    assert event.created_at.utcoffset() == timedelta(0)
    assert before <= event.created_at <= after


def test_ac06_new_causation_id_is_none_unless_given():
    assert Event.new(**new_kwargs()).causation_id is None
    assert Event.new(**new_kwargs(causation_id=None)).causation_id is None


def test_ac06_new_keeps_a_given_causation_id():
    cause = Event.new(**new_kwargs())
    effect = Event.new(**new_kwargs(causation_id=cause.event_id))
    assert effect.causation_id == cause.event_id
    assert effect.event_id != cause.event_id


@pytest.mark.parametrize(
    "overrides",
    [
        {"actor": "robot"},
        {"type": "TaskExploded"},
        {"payload": ["not", "an", "object"]},
        {"payload": {"bad": {1, 2, 3}}},
        {"stream": ""},
    ],
    ids=["invalid-actor", "unknown-type", "non-object-payload", "non-json-payload", "empty-stream"],
)
def test_ac06_new_applies_the_envelope_rules(overrides):
    with pytest.raises(ValidationError) as excinfo:
        Event.new(**new_kwargs(**overrides))
    (field,) = overrides
    assert field in {error["loc"][0] for error in excinfo.value.errors()}


def test_ac06_stored_event_new_raises_because_no_seq_is_supplied():
    with pytest.raises(ValidationError) as excinfo:
        StoredEvent.new(**new_kwargs())
    assert [error["loc"] for error in excinfo.value.errors()] == [("seq",)]


# --- AC7: type is one of the 11 names --------------------------------------------------


@pytest.mark.parametrize("name", EVENT_TYPE_NAMES)
def test_ac07_type_accepts_phase1_name(name):
    event = Event(**event_kwargs(type=name))
    assert event.type == EventType(name)
    assert event.type == name


@pytest.mark.parametrize("name", EVENT_TYPE_NAMES)
def test_ac07_type_accepts_event_type_member(name):
    event = Event(**event_kwargs(type=EventType(name)))
    assert event.type is EventType(name)


@pytest.mark.parametrize("name", ["TaskExploded", "ApprovalGiven", "TaskInvalidated"])
def test_ac07_type_rejects_unknown_or_removed_name(name):
    with pytest.raises(ValidationError):
        Event(**event_kwargs(type=name))


# --- AC8: payload is a JSON object ------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"s": "text"},
        {"i": 1},
        {"f": 1.5},
        {"t": True, "f": False},
        {"n": None},
        {"l": [1, "two", None, [3], {"four": 4}]},
        {"o": {"inner": {"deeper": []}}},
        NESTED_PAYLOAD,
    ],
    ids=["empty", "string", "int", "float", "bools", "null", "list", "object", "mixed-nested"],
)
def test_ac08_payload_accepts_json_object(payload):
    event = Event(**event_kwargs(payload=payload))
    assert event.payload == payload


@pytest.mark.parametrize(
    "payload",
    [[], [{"a": 1}], "a string", '{"a": 1}', 42, 1.5, True, None],
    ids=["empty-list", "list-of-objects", "string", "json-text", "int", "float", "bool", "none"],
)
def test_ac08_payload_rejects_top_level_non_object(payload):
    with pytest.raises(ValidationError):
        Event(**event_kwargs(payload=payload))


@pytest.mark.parametrize(
    "payload",
    [
        {"bad": {1, 2, 3}},
        {"bad": object()},
        {"outer": {"bad": {1, 2}}},
        {"items": [1, object()]},
        {"bad": float("nan")},
        {"bad": float("inf")},
        {"bad": [float("-inf")]},
        {"outer": {"bad": float("nan")}},
    ],
    ids=[
        "set",
        "arbitrary-object",
        "nested-set",
        "object-in-list",
        "nan",
        "inf",
        "minus-inf",
        "nested-nan",
    ],
)
def test_ac08_payload_rejects_non_json_value(payload):
    with pytest.raises(ValidationError):
        Event(**event_kwargs(payload=payload))


LONE_SURROGATE = "\ud800"
SURROGATE_ESCAPED = b"caf\xe9.txt".decode("utf-8", "surrogateescape")


@pytest.mark.parametrize(
    "payload",
    [
        {LONE_SURROGATE: 1},
        {"a": LONE_SURROGATE},
        {"outer": {"inner": LONE_SURROGATE}},
        {"outer": {LONE_SURROGATE: 1}},
        {"items": ["ok", LONE_SURROGATE]},
        {"path": SURROGATE_ESCAPED},
        {"ok": 1, "bad": LONE_SURROGATE},
        {"ok": 1, LONE_SURROGATE: 2},
    ],
    ids=[
        "key",
        "value",
        "nested-value",
        "nested-key",
        "in-list",
        "surrogateescape-value",
        "value-in-later-entry",
        "key-in-later-entry",
    ],
)
@pytest.mark.parametrize("model", [Event, StoredEvent], ids=["Event", "StoredEvent"])
def test_ac08_payload_rejects_string_that_is_not_valid_unicode(model, payload):
    kwargs = event_kwargs(payload=payload)
    if model is StoredEvent:
        kwargs["seq"] = 1
    with pytest.raises(ValidationError) as excinfo:
        model(**kwargs)
    assert [error["loc"] for error in excinfo.value.errors()] == [("payload",)]


def test_ac08_payload_accepts_non_ascii_text():
    payload = {"naïve": "café ☕ 日本語 😀"}
    event = Event(**event_kwargs(payload=payload))
    assert Event.model_validate_json(event.model_dump_json()).payload == payload


# An integer of 4300 or more digits is written by model_dump_json() but cannot be read back.
UNREADABLE_INT = 10**4299


@pytest.mark.parametrize(
    "payload",
    [
        {"n": UNREADABLE_INT},
        {"n": -UNREADABLE_INT},
        {"n": 10**4300},
        {"outer": [{"n": UNREADABLE_INT}]},
        {"ok": 1, "n": UNREADABLE_INT},
    ],
    ids=["positive", "negative", "larger", "nested", "in-later-entry"],
)
@pytest.mark.parametrize("model", [Event, StoredEvent], ids=["Event", "StoredEvent"])
def test_ac08_payload_rejects_integer_too_large_to_read_back(model, payload):
    kwargs = event_kwargs(payload=payload)
    if model is StoredEvent:
        kwargs["seq"] = 1
    with pytest.raises(ValidationError) as excinfo:
        model(**kwargs)
    assert [error["loc"] for error in excinfo.value.errors()] == [("payload",)]


@pytest.mark.parametrize(
    "value",
    [UNREADABLE_INT - 1, -(UNREADABLE_INT - 1), 2**64, -(2**63) - 1, 10**400],
    ids=["largest-positive", "largest-negative", "two-to-the-64", "below-int64", "ten-to-the-400"],
)
def test_ac08_payload_accepts_large_integer_that_round_trips(value):
    event = Event(**event_kwargs(payload={"n": value, "nested": [{"n": value}]}))
    restored = Event.model_validate_json(event.model_dump_json())
    assert restored == event
    assert restored.payload["n"] == value


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_ac08_payload_rejects_non_finite_token_in_json_text(token):
    text = Event(**event_kwargs(payload={"x": 1})).model_dump_json()
    assert '"x":1' in text
    with pytest.raises(ValidationError):
        Event.model_validate_json(text.replace('"x":1', f'"x":{token}'))


# --- AC9: actor matches ^(human|orchestrator|agent:[a-z][a-z-]*)$ -----------------------


@pytest.mark.parametrize(
    "actor",
    [
        "human",
        "orchestrator",
        "agent:planner",
        "agent:implementer",
        "agent:reviewer",
        "agent:test-writer",
    ],
)
def test_ac09_actor_accepts(actor):
    assert Event(**event_kwargs(actor=actor)).actor == actor


@pytest.mark.parametrize(
    "actor",
    [
        "",
        "robot",
        "Human",
        "agent:",
        "agent:Implementer",
        "agent:1x",
        "agent:-x",
        "agent:implementer ",
        "human\n",
    ],
    ids=[
        "empty",
        "robot",
        "capitalised-human",
        "agent-without-role",
        "capitalised-role",
        "role-starting-with-digit",
        "role-starting-with-hyphen",
        "trailing-space",
        "trailing-newline",
    ],
)
def test_ac09_actor_rejects(actor):
    with pytest.raises(ValidationError):
        Event(**event_kwargs(actor=actor))


# --- AC10: created_at is timezone-aware UTC ---------------------------------------------


@pytest.mark.parametrize(
    "value",
    [BASELINE_INSTANT, BASELINE_ISO, "2026-10-08T12:00:00+00:00"],
    ids=["aware-utc-datetime", "iso-string-with-z", "iso-string-with-zero-offset"],
)
def test_ac10_created_at_accepts_aware_utc(value):
    event = Event(**event_kwargs(created_at=value))
    assert isinstance(event.created_at, datetime)
    assert event.created_at.tzinfo is not None
    assert event.created_at.utcoffset() == timedelta(0)
    assert event.created_at == BASELINE_INSTANT


@pytest.mark.parametrize(
    "value",
    [datetime(2026, 10, 8, 12, 0), "2026-10-08T12:00:00"],
    ids=["naive-datetime", "naive-iso-string"],
)
def test_ac10_created_at_rejects_naive(value):
    with pytest.raises(ValidationError):
        Event(**event_kwargs(created_at=value))


@pytest.mark.parametrize(
    "value",
    [1759924800, 1759924800.5, "1759924800"],
    ids=["int", "float", "numeric-string"],
)
def test_ac10_created_at_rejects_numeric_timestamp(value):
    with pytest.raises(ValidationError) as excinfo:
        Event(**event_kwargs(created_at=value))
    assert [error["loc"] for error in excinfo.value.errors()] == [("created_at",)]


@pytest.mark.parametrize("model", [Event, StoredEvent], ids=["Event", "StoredEvent"])
@pytest.mark.parametrize("number", ["1759924800", "1759924800.5"], ids=["int", "float"])
def test_ac10_created_at_rejects_bare_number_in_json_text(model, number):
    text = StoredEvent(**event_kwargs(seq=1)).model_dump_json(include=set(model.model_fields))
    dumped_created_at = json.dumps(json.loads(text)["created_at"])
    assert text.count(dumped_created_at) == 1
    numeric_text = text.replace(dumped_created_at, number)
    assert json.loads(numeric_text)["created_at"] == json.loads(number)
    with pytest.raises(ValidationError) as excinfo:
        model.model_validate_json(numeric_text)
    assert [error["loc"] for error in excinfo.value.errors()] == [("created_at",)]


def test_ac10_created_at_accepts_iso_string_in_json_text():
    text = Event(**event_kwargs()).model_dump_json()
    restored = Event.model_validate_json(text)
    assert restored.created_at == BASELINE_INSTANT
    assert restored.created_at.utcoffset() == timedelta(0)


# --- AC11: a non-UTC offset is converted to UTC -----------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 10, 8, 17, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        "2026-10-08T17:30:00+05:30",
        datetime(2026, 10, 8, 5, 0, tzinfo=timezone(timedelta(hours=-7))),
        "2026-10-08T05:00:00-07:00",
    ],
    ids=["datetime-plus-0530", "string-plus-0530", "datetime-minus-0700", "string-minus-0700"],
)
def test_ac11_created_at_converts_non_utc_offset_to_utc(value):
    event = Event(**event_kwargs(created_at=value))
    assert event.created_at.utcoffset() == timedelta(0)
    assert event.created_at == BASELINE_INSTANT
    assert (event.created_at.hour, event.created_at.minute) == (12, 0)


OUT_OF_RANGE_IN_UTC = {
    "year-1-positive-offset": "0001-01-01T00:00:00+05:00",
    "year-9999-negative-offset": "9999-12-31T23:59:59-05:00",
}


@pytest.mark.parametrize("value", OUT_OF_RANGE_IN_UTC.values(), ids=OUT_OF_RANGE_IN_UTC.keys())
@pytest.mark.parametrize("form", ["string", "datetime", "json-text"])
def test_ac11_created_at_not_representable_in_utc_is_a_validation_error(value, form):
    with pytest.raises(ValidationError) as excinfo:
        if form == "string":
            Event(**event_kwargs(created_at=value))
        elif form == "datetime":
            Event(**event_kwargs(created_at=datetime.fromisoformat(value)))
        else:
            text = Event(**event_kwargs()).model_dump_json()
            assert f'"{BASELINE_ISO}"' in text
            Event.model_validate_json(text.replace(f'"{BASELINE_ISO}"', f'"{value}"'))
    assert [error["loc"] for error in excinfo.value.errors()] == [("created_at",)]


# --- AC12: created_at serialises as ISO 8601 with a UTC designator ----------------------


@pytest.mark.parametrize(
    "value",
    [BASELINE_INSTANT, BASELINE_ISO, "2026-10-08T17:30:00+05:30"],
    ids=["aware-utc-datetime", "iso-string-with-z", "non-utc-offset"],
)
def test_ac12_created_at_dumps_as_iso8601_utc_string(value):
    dumped = json.loads(Event(**event_kwargs(created_at=value)).model_dump_json())
    created_at = dumped["created_at"]
    assert isinstance(created_at, str)
    assert created_at.endswith(("Z", "+00:00"))
    parsed = datetime.fromisoformat(created_at)
    assert parsed.utcoffset() == timedelta(0)
    assert parsed == BASELINE_INSTANT


# --- AC13: StoredEvent is Event plus a required integer seq -----------------------------


def test_ac13_stored_event_is_a_subclass_of_event():
    assert issubclass(StoredEvent, Event)
    assert StoredEvent is not Event


def test_ac13_stored_event_adds_exactly_one_field_seq():
    assert set(StoredEvent.model_fields) - set(Event.model_fields) == {"seq"}
    assert set(StoredEvent.model_fields) == ENVELOPE_FIELDS | {"seq"}
    assert StoredEvent.model_fields["seq"].is_required()


def test_ac13_stored_event_exposes_integer_seq():
    stored = StoredEvent(**event_kwargs(seq=7))
    assert stored.seq == 7
    assert type(stored.seq) is int
    assert isinstance(stored, Event)


def test_ac13_stored_event_requires_seq():
    with pytest.raises(ValidationError) as excinfo:
        StoredEvent(**event_kwargs())
    assert [error["loc"] for error in excinfo.value.errors()] == [("seq",)]


@pytest.mark.parametrize(
    "seq",
    ["abc", "7", 7.0, 1.5, True, None, [1]],
    ids=["word", "digit-string", "whole-float", "fraction", "bool", "none", "list"],
)
def test_ac13_stored_event_rejects_non_integer_seq(seq):
    with pytest.raises(ValidationError) as excinfo:
        StoredEvent(**event_kwargs(seq=seq))
    assert [error["loc"] for error in excinfo.value.errors()] == [("seq",)]


@pytest.mark.parametrize("seq", [0, -1], ids=["zero", "negative"])
def test_ac13_stored_event_rejects_seq_below_one(seq):
    with pytest.raises(ValidationError) as excinfo:
        StoredEvent(**event_kwargs(seq=seq))
    assert [error["loc"] for error in excinfo.value.errors()] == [("seq",)]


@pytest.mark.parametrize("seq", [1, 2**40], ids=["one", "two-to-the-forty"])
def test_ac13_stored_event_accepts_positive_integer_seq(seq):
    stored = StoredEvent(**event_kwargs(seq=seq))
    assert stored.seq == seq
    assert type(stored.seq) is int


def test_ac13_stored_event_keeps_the_event_envelope_rules():
    with pytest.raises(ValidationError):
        StoredEvent(**event_kwargs(seq=1, actor="robot"))
    with pytest.raises(ValidationError):
        StoredEvent(**event_kwargs(seq=1, type="TaskExploded"))
    with pytest.raises(ValidationError):
        StoredEvent(**event_kwargs(seq=1, created_at=datetime(2026, 10, 8, 12, 0)))


# --- AC14: JSON round trip --------------------------------------------------------------


def test_ac14_event_survives_json_round_trip():
    original = Event(
        **event_kwargs(
            event_id=uuid4(),
            payload=NESTED_PAYLOAD,
            actor="agent:test-writer",
            causation_id=str(uuid4()),
        )
    )
    restored = Event.model_validate_json(original.model_dump_json())
    assert type(restored) is Event
    assert restored == original
    assert restored.payload == NESTED_PAYLOAD


def test_ac14_event_without_causation_id_survives_json_round_trip():
    kwargs = event_kwargs()
    assert "causation_id" not in kwargs
    original = Event(**kwargs)
    restored = Event.model_validate_json(original.model_dump_json())
    assert restored == original
    assert restored.event_id == kwargs["event_id"]
    assert restored.causation_id is None


def test_ac14_event_made_by_new_survives_json_round_trip():
    original = Event.new(
        stream="task:AUTH-002",
        type="TaskStateChanged",
        payload=NESTED_PAYLOAD,
        actor="agent:test-writer",
    )
    restored = Event.model_validate_json(original.model_dump_json())
    assert restored == original
    assert restored.event_id == original.event_id
    assert restored.created_at == original.created_at


def test_ac14_stored_event_survives_json_round_trip():
    original = StoredEvent(
        **event_kwargs(seq=42, event_id=uuid1(), payload=NESTED_PAYLOAD, actor="human")
    )
    restored = StoredEvent.model_validate_json(original.model_dump_json())
    assert type(restored) is StoredEvent
    assert restored == original
    assert restored.seq == 42


def test_ac14_dumped_json_holds_payload_as_an_object_under_the_column_names():
    dumped = json.loads(
        StoredEvent(**event_kwargs(seq=1, payload=NESTED_PAYLOAD)).model_dump_json()
    )
    assert set(dumped) == ENVELOPE_FIELDS | {"seq"}
    assert dumped["payload"] == NESTED_PAYLOAD
    assert dumped["type"] == "TaskStateChanged"


# --- AC15: the domain module imports no infrastructure ----------------------------------

MODULE_NAME = "openfactory.domain.events"
MODULE_PACKAGE = "openfactory.domain"
FORBIDDEN_IMPORTS = [
    "openfactory.adapters",
    "openfactory.app",
    "openfactory.ports",
    "sqlite3",
    "subprocess",
    "socket",
]


def imported_module_names():
    """Absolute dotted names imported anywhere in the module under test.

    `from a import b` yields both `a` and `a.b`, because `b` may be a submodule.
    Relative imports are resolved against the module's package.
    """
    spec = importlib.util.find_spec(MODULE_NAME)
    assert spec is not None and spec.origin is not None, f"module {MODULE_NAME} does not exist"
    path = Path(spec.origin)
    assert path.is_file(), f"{path} is not a file"

    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package_parts = MODULE_PACKAGE.split(".")
                base_parts = package_parts[: len(package_parts) - (node.level - 1)]
                base = ".".join(base_parts + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
    return names


def test_ac15_domain_events_module_can_be_parsed_for_imports():
    assert imported_module_names(), f"{MODULE_NAME} has no imports to inspect"


@pytest.mark.parametrize("forbidden", FORBIDDEN_IMPORTS)
def test_ac15_domain_events_does_not_import(forbidden):
    offending = sorted(
        name
        for name in imported_module_names()
        if name == forbidden or name.startswith(forbidden + ".")
    )
    assert offending == [], f"{MODULE_NAME} imports {offending}"


# --- AC16: unknown fields are rejected on both models -----------------------------------


def assert_only_extra_field_error(error, field):
    assert [(item["loc"], item["type"]) for item in error.errors()] == [
        ((field,), "extra_forbidden")
    ]


def test_ac16_event_rejects_seq():
    with pytest.raises(ValidationError) as excinfo:
        Event(**event_kwargs(seq=5))
    assert_only_extra_field_error(excinfo.value, "seq")


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [(Event, {}), (StoredEvent, {"seq": 1})],
    ids=["Event", "StoredEvent"],
)
def test_ac16_misspelt_field_is_rejected(model, kwargs):
    with pytest.raises(ValidationError) as excinfo:
        model(**event_kwargs(causation=uuid4(), **kwargs))
    assert_only_extra_field_error(excinfo.value, "causation")


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [(Event, {}), (StoredEvent, {"seq": 1})],
    ids=["Event", "StoredEvent"],
)
def test_ac16_extra_key_in_json_text_is_rejected(model, kwargs):
    document = json.loads(model(**event_kwargs(**kwargs)).model_dump_json())
    document["unexpected"] = "value"
    with pytest.raises(ValidationError) as excinfo:
        model.model_validate_json(json.dumps(document))
    assert_only_extra_field_error(excinfo.value, "unexpected")


def test_ac16_event_rejects_seq_in_json_text():
    text = StoredEvent(**event_kwargs(seq=5)).model_dump_json()
    assert StoredEvent.model_validate_json(text).seq == 5
    with pytest.raises(ValidationError) as excinfo:
        Event.model_validate_json(text)
    assert_only_extra_field_error(excinfo.value, "seq")


# --- AC17: stream is non-empty, with no format imposed ----------------------------------


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [(Event, {}), (StoredEvent, {"seq": 1})],
    ids=["Event", "StoredEvent"],
)
def test_ac17_stream_rejects_empty_string(model, kwargs):
    with pytest.raises(ValidationError) as excinfo:
        model(**event_kwargs(stream="", **kwargs))
    assert [error["loc"] for error in excinfo.value.errors()] == [("stream",)]


@pytest.mark.parametrize("stream", ["task:AUTH-002", "x", "spec"])
def test_ac17_stream_accepts_any_non_empty_string(stream):
    assert Event(**event_kwargs(stream=stream)).stream == stream
