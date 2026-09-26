"""The frozen retrieval benchmark fixture: a fictional tidal power station (decisions.md D-213, D-225 reading 10; V1.3 Step 4, phase C).

The corpus is 12 documents in 6 sources, one paragraph per chunk, at most 60 words a chunk (the semantic model's word-piece check needs its tokenizer and runs at Step 5); a byte-identical
mirror of one document under a second source (``archive``); a source (``outreach``) that restates another source's facts in other words, undeclared; and distractor documents that reuse the
queries' vocabulary. The queries are 36, English only: 6 development queries (debugging only) and 30 frozen test queries. Each stratum is defined by construction and checked mechanically by
``tests/unit/knowledge/test_knowledge_benchmark_fixture.py`` from this module's own fixed stop list, never from what any retriever returns:

- ``lexical``: the query shares at least two content tokens with every gold chunk;
- ``paraphrase``: the query shares no content token with any gold chunk;
- ``multi_source``: the gold chunks lie in at least three distinct sources;
- ``distractor``: the query shares at least two content tokens with some chunk that is not gold.

Gold labels are over content-equivalence groups (chunks of identical text): the mirror pair is one group. Every chunk that states the fact is gold, the restating source's included.

**This module is frozen.** Its digest is pinned in ``test_knowledge_benchmark_fixture.py`` and was recorded before the first retrieval run; nothing here is tuned against any result, and a
change to it is a change of benchmark, recorded as one. It holds no retrieval, no clock and no I/O.
"""

import hashlib
import json
import re
from dataclasses import dataclass

from eidos.knowledge import ChunkingScheme, KnowledgeChunk, KnowledgeDocument, KnowledgeSnapshot, build_snapshot

BENCHMARK_VERSION = "kestrel-reach-v1"
KB_ID = "kestrel-reach"
CHUNKING = ChunkingScheme(max_words=60)
MAX_CHUNK_WORDS = 60

STOP_WORDS = frozenset(
    """a about above after again all also an and any are as at be been before being between both but by can could did do does each few for from had has have he her his how i if in into is it
    its may more most must no nor not of on once one only or other our out over own per same shall she should so some such than that the their them then there these they this those three
    through to too two under until up very was we were what when where which while who whom why will with would you your""".split()
)


@dataclass(frozen=True)
class FixtureDocument:
    key: str
    source_id: str
    paragraphs: tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)


@dataclass(frozen=True)
class FixtureQuery:
    query_id: str
    split: str  # "dev" or "test"
    stratum: str  # "lexical", "paraphrase", "multi_source" or "distractor"
    text: str
    gold: tuple[tuple[str, int], ...]  # (document key, paragraph index): every chunk that states the fact


# --- the corpus -------------------------------------------------------------------------------------------------------------------------

OPS_STARTUP = (
    "Restart after a Red Shutdown begins with the duty engineer completing the written inspection checklist, Form KR-14, for every turbine bay. No turbine may be released for restart until "
    "all six bays carry a signed checklist. The checklist must be filed in the operations log before the barrier gates are lifted.",
    "The Skerry Gate sensors must report normal readings for forty minutes before the gates are lifted. Normal means the tilt sensors read below two degrees and the seal pressure gauges stay "
    "within the green band marked on each panel. Any amber reading restarts the forty minute count from zero.",
    "Turbines are restarted one at a time in the order T1, T3, T5, T2, T4, T6. The duty engineer waits for the previous turbine to reach synchronous speed, which takes roughly eleven minutes, "
    "before releasing the next. A turbine that trips twice is isolated and reported on Form KR-22.",
    "The shift supervisor counter-signs the restart record after the third turbine is online. Until that signature is present the station may not export more than one third of its rated "
    "output. The counter-signature is recorded with the time to the nearest minute.",
    "After all six turbines are online the duty engineer telephones the grid control room and reads out the restart record number. Grid control acknowledges by reading the number back. The "
    "call is logged on the reverse of Form KR-14 and the log page is initialled by both parties.",
)

OPS_STORM_SHUTDOWN = (
    "A Red Shutdown is ordered when the forecast surge exceeds three point four metres above chart datum or when wind at the barrier mast exceeds thirty metres per second for ten consecutive "
    "minutes. Only the shift supervisor may order it, and the order is spoken aloud twice on the station channel.",
    "On a Red Shutdown the barrier gates are lowered first, before any turbine is braked, so that debris is not drawn into the runners. Each gate lowering takes six minutes. The duty engineer "
    "confirms every gate with the seated-latch indicator and writes the confirmation time on the shutdown card.",
    "Turbines are braked in the reverse of their restart order, beginning with T6. Braking uses the hydraulic disc first and the electrical dump load second, never both at once. A turbine "
    "must be stationary for two minutes before its bay hatch is sealed.",
    "Non-essential staff leave the barrier walkway within fifteen minutes of the order and muster at the landward lodge. The harbourmaster is told the shutdown time so that vessel movements "
    "through the estuary can be suspended. A headcount is taken at the lodge and reported to the shift supervisor.",
    "An Amber Watch is a lesser state declared when the forecast surge lies between two point eight and three point four metres. Under Amber Watch all turbines keep running but the barrier "
    "walkway is closed and the duty engineer re-reads the forecast hourly. Amber Watch does not require the restart checklist.",
)

SAFETY_AUDIT = (
    "The autumn audit examined the restart records for the previous twelve months and found that forty one of forty four restarts followed the written checklist. Three restarts released a "
    "turbine before the checklist was signed. All three occurred on night shifts during the same fortnight.",
    "The auditors recommended that no turbine may be released to the grid until the shift supervisor has signed both the checklist and the restart record. The Safety Office regards the "
    "second signature as the single most effective control against premature release.",
    "Lifejacket inspection was found to be satisfactory, but eleven of sixty lifejackets on the barrier walkway had inflation cartridges past their date. Replacement cartridges were fitted "
    "within a week and the walkway store was added to the monthly inspection round.",
    "Emergency lighting on the seaward stairs failed the ninety minute discharge test in two of eight fittings. The fittings were replaced with sealed units rated for a full three hours. The "
    "retest in the following month passed without comment.",
    "The audit found that shutdown drills are held twice a year but attended by fewer than half of the staff. It recommended that attendance be recorded and that any shift missing two "
    "consecutive drills receive a supervised walkthrough with the duty engineer.",
)

SAFETY_INCIDENTS = (
    "Incident KR-IR-31 records a gate latch that did not seat during a storm shutdown. The duty engineer noticed the unlit indicator and reseated the latch by hand using the emergency lever. "
    "The gate was raised again briefly to clear a stranded timber log, then lowered without further trouble.",
    "Incident KR-IR-32 records a contractor who entered the turbine bay for T4 without a permit. The bay was locked out at once and the contractor was escorted to the lodge. The contractor's "
    "company was reminded in writing that entry needs a permit from the shift supervisor.",
    "Incident KR-IR-33 records a small hydraulic leak beneath the T2 braking disc. Oil was contained by the bund and none reached the estuary. The disc seals were replaced during the next "
    "scheduled slack-water window and the bund was cleaned and tested.",
    "Incident KR-IR-34 records a false alarm from the fire panel in the transformer hall, caused by condensation on a smoke detector. The hall was searched and found clear. The detector was "
    "dried, cleaned and moved away from the ventilation outlet.",
)

MAINTENANCE_SCHEDULE = (
    "Each turbine receives a full mechanical service every four thousand running hours or every eighteen months, whichever falls first. The service covers the gearbox oil, the yaw drive, "
    "the blade root bolts and the braking disc thickness. A turbine under service is marked out of use on the operations board.",
    "Gearbox oil is sampled every five hundred running hours and sent to the contract laboratory in Fenwick. The sample is compared with the previous three results, and a rising iron count is "
    "escalated to the maintenance planner at once. Oil is changed only when the laboratory recommends it.",
    "Blade root bolts are torque-checked by hand at every service and by ultrasonic gauge once a year. Any bolt found more than five percent below specification is replaced together with its "
    "two neighbours. The torque record is kept in the maintenance file for the life of the turbine.",
    "Services are planned for slack water at neap tides, when the flow through the barrier is weakest. No more than one turbine may be out of use for service at any time, and two consecutive "
    "services may not begin within seven days of each other. The planner publishes the schedule a month ahead.",
    "The barrier gate hydraulics are serviced separately in April and October. The service replaces filter elements, checks accumulator pre-charge and exercises each gate through a full raise "
    "and lower cycle. The tests are witnessed by the duty engineer, who signs the gate test sheet.",
)

MAINTENANCE_SPARES = (
    "The spares store holds two complete sets of braking disc pads, six spare gearbox oil filters and four sealed bearing cartridges. Stock levels are counted on the first Monday of each "
    "month. Any item falling below its minimum triggers an order to the approved vendor without further approval.",
    "Braking discs are supplied by Halvorsen Marine, with a lead time of nine weeks. Because the lead time is long, one spare disc is kept ready for immediate use. Halvorsen Marine also "
    "offers a rapid service in which a disc is reground and returned within three weeks.",
    "Gearbox oil is bought in two hundred litre drums from Tarn Lubricants. Drums are stored upright in the bunded oil room and used in the order received. Opened drums are dated and "
    "discarded after ninety days, whatever quantity remains.",
    "Hand tools are issued from the tool crib against a numbered tag and returned at the end of the shift. A missing tool is reported to the shift supervisor immediately, because a tool lost "
    "inside a turbine bay can cause serious damage when the turbine is restarted.",
)

GRID_AGREEMENT = (
    "The station shall notify Northwold Grid at least thirty minutes before reconnecting any turbine after a shutdown. The notice is given by telephone to the grid control room and confirmed "
    "by the read-back of the restart record number. Reconnection without notice is a breach of the connection agreement.",
    "During a storm shutdown the station shall inform Northwold Grid within five minutes of the order and give an estimate of the time to restart. The estimate is updated every thirty "
    "minutes until the station reports that all six turbines are ready for restart.",
    "The maximum export of the station is fourteen megawatts. Northwold Grid may instruct the station to reduce export to zero at any time for system security, and the station shall comply "
    "within two minutes of the instruction being given by telephone.",
    "Payment for exported energy is settled monthly on the basis of the meter readings agreed by both parties. Meter faults are reported to Northwold Grid within one working day. Where a "
    "fault makes readings unreliable, the export for the affected period is estimated from the previous four weeks.",
)

VISITOR_GUIDE = (
    "Visitors to Kestrel Reach are welcome on guided tours of the turbine hall on weekday afternoons. Each tour includes an inspection of the viewing gallery and a short film about the "
    "tides. Tours may be cancelled at short notice after a storm shutdown, and visitors are asked to check the noticeboard.",
    "Every visitor receives a safety checklist card at the lodge and must sign the visitor log before entering the turbine hall. Children under twelve must be accompanied. Sturdy shoes are "
    "advised because the barrier walkway can be wet and slippery even in calm weather.",
    "The lodge cafe serves hot drinks and light meals, and its terrace overlooks the estuary. Restart of the kettle after the afternoon rush takes about ten minutes. Vegetarian and "
    "gluten-free options are available on request, and the cafe accepts card payments only.",
    "School groups can book a talk from a station engineer about how the turbines are inspected and serviced. The talk lasts forty minutes and includes a chance to handle a spare bearing "
    "cartridge. Bookings are taken by email at least a fortnight ahead.",
)

NEWS_BULLETIN = (
    "Every turbine at the station gets a thorough overhaul after four thousand hours of operation or eighteen months, whichever arrives sooner. Engineers check the gearbox lubricant, the "
    "steering drive, the bolts at the base of each blade and how worn the brake disc has become.",
    "Lubricant from each gearbox is tested every five hundred hours of running by a laboratory in Fenwick. Technicians compare each result with the last three, and a climbing level of iron is "
    "passed straight to the planner. The oil itself is only replaced on the laboratory's advice.",
    "Bolts at the root of every blade are tightened and checked by hand at each overhaul and with an ultrasound gauge yearly. A bolt found over five percent loose is swapped along with the "
    "two next to it, and the record stays on file for the turbine's whole life.",
    "Overhauls are scheduled for the calm period around neap tides. Only one turbine may be stopped for work at once, and two overhauls cannot start within a week of each other. The planner "
    "announces the timetable a month in advance.",
)

STAFF_NEWSLETTER = (
    "Congratulations to the duty engineer team on a year without a lost-time accident. The shift supervisor rota has been refreshed, and the new pattern starts in the first week of March. "
    "Staff who wish to swap shifts should tell the supervisor at least three days ahead.",
    "The annual staff barbecue will be held at the landward lodge on the last Saturday of June, weather permitting. A storm shutdown would postpone it by a week. Volunteers are needed to "
    "bring salads, and the harbourmaster has kindly offered to run the grill.",
    "A reminder that the turbine hall car park is closed for resurfacing next month. Staff should use the field behind the lodge. The gates to the field are locked at night, and the "
    "checklist for opening and closing them is pinned inside the security cabin.",
    "Lost property from the barrier walkway now includes two lifejackets, a green thermos and a pair of reading glasses. Owners may collect them from the lodge reception. Anything unclaimed "
    "after a month will be given to the local charity shop.",
)

TRAINING_SYLLABUS = (
    "The induction course for new staff runs for five days and covers site safety, the restart checklist, tidal theory and first aid. Trainees shadow a duty engineer during at least two "
    "shifts. Assessment is by a written test and a supervised walk-through of the shutdown card.",
    "Advanced training in turbine maintenance is offered every spring in partnership with the technical college at Fenwick. The course covers gearbox oil analysis, blade bolt torque checking "
    "and hydraulic disc servicing. Places are limited to eight trainees and are allocated by the maintenance planner.",
    "Grid connection training explains how a tidal station exports energy and why the grid operator must be told before a reconnection. It is a half-day classroom session with a short quiz. "
    "Certificates are valid for three years and renewed by a refresher session.",
    "First aid certificates must be renewed every three years. The station holds an emergency defibrillator in the lodge and another in the turbine hall. Trainees learn where each is kept "
    "and practise using a training unit under supervision.",
)

DOCUMENTS = (
    FixtureDocument("ops-startup", "ops", OPS_STARTUP),
    FixtureDocument("ops-storm-shutdown", "ops", OPS_STORM_SHUTDOWN),
    FixtureDocument("safety-audit", "safety", SAFETY_AUDIT),
    FixtureDocument("safety-incidents", "safety", SAFETY_INCIDENTS),
    FixtureDocument("maint-schedule", "maint", MAINTENANCE_SCHEDULE),
    FixtureDocument("maint-spares", "maint", MAINTENANCE_SPARES),
    FixtureDocument("grid-agreement", "grid", GRID_AGREEMENT),
    FixtureDocument("archive-audit-copy", "archive", SAFETY_AUDIT),  # byte-identical to safety-audit: the same tuple of paragraphs
    FixtureDocument("outreach-visitor-guide", "outreach", VISITOR_GUIDE),
    FixtureDocument("outreach-news-bulletin", "outreach", NEWS_BULLETIN),  # restates maint-schedule paragraphs 0 to 3 in other words, undeclared
    FixtureDocument("outreach-staff-newsletter", "outreach", STAFF_NEWSLETTER),
    FixtureDocument("outreach-training-syllabus", "outreach", TRAINING_SYLLABUS),
)

# --- the queries ------------------------------------------------------------------------------------------------------------------------

QUERIES = (
    # lexical overlap: test
    FixtureQuery("L01", "test", "lexical", "How long must the Skerry Gate sensors report normal readings before the gates are lifted?", (("ops-startup", 1),)),
    FixtureQuery("L02", "test", "lexical", "In what order are the turbines restarted and how long does each take to reach synchronous speed?", (("ops-startup", 2),)),
    FixtureQuery("L03", "test", "lexical", "Which vendor supplies the braking discs and what is the lead time?", (("maint-spares", 1),)),
    FixtureQuery("L04", "test", "lexical", "What is the maximum export of the station in megawatts?", (("grid-agreement", 2),)),
    FixtureQuery("L05", "test", "lexical", "Who may order a Red Shutdown and how is the order spoken?", (("ops-storm-shutdown", 0),)),
    FixtureQuery("L06", "test", "lexical", "How many restarts followed the written checklist in the autumn audit?", (("safety-audit", 0),)),
    FixtureQuery("L07", "test", "lexical", "What did incident KR-IR-33 record about the T2 braking disc?", (("safety-incidents", 2),)),
    FixtureQuery("L08", "test", "lexical", "How often is the barrier gate hydraulics service carried out?", (("maint-schedule", 4),)),
    # lexical overlap: development
    FixtureQuery("LD1", "dev", "lexical", "When is an Amber Watch declared?", (("ops-storm-shutdown", 4),)),
    FixtureQuery("LD2", "dev", "lexical", "Which incident records a gate latch that did not seat?", (("safety-incidents", 0),)),
    # paraphrase: test
    FixtureQuery(
        "P01", "test", "paraphrase",
        "Which paperwork must the person on watch fill in for each machine housing prior to bringing the plant back into service?", (("ops-startup", 0),),
    ),
    FixtureQuery(
        "P02", "test", "paraphrase",
        "During a severe weather closure, which comes earlier, sealing the sea wall openings or halting the power generators, and how long does each opening take?",
        (("ops-storm-shutdown", 1),),
    ),
    FixtureQuery(
        "P03", "test", "paraphrase",
        "How much warning must the plant give the electricity network company ahead of returning a generator onto the wires after a stoppage?", (("grid-agreement", 0),),
    ),
    FixtureQuery(
        "P04", "test", "paraphrase",
        "Which standby luminaires beside the steps by the water did not survive the long battery trial, and what was fitted afterwards?", (("safety-audit", 3),),
    ),
    FixtureQuery(
        "P05", "test", "paraphrase",
        "How long can a broached barrel of transmission lubricant stay in use before it is thrown away, and where are the barrels kept?", (("maint-spares", 2),),
    ),
    FixtureQuery(
        "P06", "test", "paraphrase",
        "Which outside worker walked into a machine chamber lacking authorisation and was led away, and whose sign-off is required to go in?", (("safety-incidents", 1),),
    ),
    FixtureQuery(
        "P07", "test", "paraphrase",
        "After a severe weather alarm, where do employees who are not vital gather, and who tells the port authority to halt boat traffic?", (("ops-storm-shutdown", 3),),
    ),
    FixtureQuery(
        "P08", "test", "paraphrase",
        "What limits how much electricity may be sent out before a second manager endorses the log after several machines are running?", (("ops-startup", 3),),
    ),
    FixtureQuery(
        "P09", "test", "paraphrase",
        "When are the stoppages for maintenance arranged to coincide with the gentlest current, and how early is the programme made public?",
        (("maint-schedule", 3), ("outreach-news-bulletin", 3)),
    ),
    FixtureQuery(
        "P10", "test", "paraphrase",
        "What is the highest amount of power the site can send to the network, and how quickly must it stop sending when told to by the network company?", (("grid-agreement", 2),),
    ),
    # paraphrase: development
    FixtureQuery(
        "PD1", "dev", "paraphrase",
        "Which lower-level alert lets the machines carry on while the footpath over the sea wall is shut?", (("ops-storm-shutdown", 4),),
    ),
    FixtureQuery(
        "PD2", "dev", "paraphrase",
        "How frequently are the rehearsals of closing the plant conducted, and what is suggested for teams that skip them repeatedly?", (("safety-audit", 4),),
    ),
    # multi-source: test
    FixtureQuery(
        "M01", "test", "multi_source", "What are the duties of the shift supervisor?",
        (("ops-startup", 3), ("ops-storm-shutdown", 0), ("ops-storm-shutdown", 3), ("safety-audit", 1), ("safety-incidents", 1), ("maint-spares", 3)),
    ),
    FixtureQuery(
        "M02", "test", "multi_source", "What must be reported to Northwold Grid and when?",
        (("grid-agreement", 0), ("grid-agreement", 1), ("grid-agreement", 3), ("ops-startup", 4), ("outreach-training-syllabus", 2)),
    ),
    FixtureQuery(
        "M03", "test", "multi_source", "Which documents say something about braking discs?",
        (("ops-storm-shutdown", 2), ("safety-incidents", 2), ("maint-spares", 0), ("maint-spares", 1), ("maint-schedule", 0), ("outreach-news-bulletin", 0)),
    ),
    FixtureQuery(
        "M04", "test", "multi_source", "What is required before a turbine is restarted after a shutdown?",
        (("ops-startup", 0), ("ops-startup", 1), ("safety-audit", 1), ("grid-agreement", 0)),
    ),
    FixtureQuery(
        "M05", "test", "multi_source", "How are the barrier gates checked and tested?",
        (("ops-storm-shutdown", 1), ("safety-incidents", 0), ("maint-schedule", 4), ("ops-startup", 1)),
    ),
    FixtureQuery(
        "M06", "test", "multi_source", "Which documents describe the duty engineer's tasks?",
        (("ops-startup", 0), ("ops-startup", 2), ("ops-startup", 4), ("ops-storm-shutdown", 1), ("ops-storm-shutdown", 4), ("safety-audit", 4), ("safety-incidents", 0), ("maint-schedule", 4)),
    ),
    # multi-source: development
    FixtureQuery(
        "MD1", "dev", "multi_source", "What must be logged, recorded or filed?",
        (("ops-startup", 0), ("ops-startup", 3), ("ops-startup", 4), ("safety-audit", 4), ("maint-schedule", 2)),
    ),
    # distractor bait: test
    FixtureQuery("B01", "test", "distractor", "Where do staff muster after the shutdown order?", (("ops-storm-shutdown", 3),)),
    FixtureQuery("B02", "test", "distractor", "Who completes the restart checklist for each turbine bay?", (("ops-startup", 0),)),
    FixtureQuery("B03", "test", "distractor", "How often are the turbines serviced and inspected?", (("maint-schedule", 0), ("outreach-news-bulletin", 0))),
    FixtureQuery("B04", "test", "distractor", "How many minutes does the station take to restart each turbine?", (("ops-startup", 2),)),
    FixtureQuery("B05", "test", "distractor", "Where are the lifejackets kept and inspected on the barrier walkway?", (("safety-audit", 2),)),
    FixtureQuery("B06", "test", "distractor", "Which staff are expected to attend the shutdown drills and how is attendance recorded?", (("safety-audit", 4),)),
    # distractor bait: development
    FixtureQuery("BD1", "dev", "distractor", "Who tells the harbourmaster about the shutdown time?", (("ops-storm-shutdown", 3),)),
)


# --- mechanical definitions (nothing here retrieves) --------------------------------------------------------------------------------------

_WORD = re.compile(r"\w+")


def content_tokens(text: str) -> frozenset[str]:
    """The tokens of ``text`` that carry content: lower-cased word runs that are not on the fixed stop list. Independent of every retriever."""
    return frozenset(token for token in _WORD.findall(text.lower()) if token not in STOP_WORDS)


def knowledge_documents() -> tuple[KnowledgeDocument, ...]:
    return tuple(KnowledgeDocument(source_id=document.source_id, text=document.text) for document in DOCUMENTS)


def build_fixture_snapshot() -> KnowledgeSnapshot:
    snapshot = build_snapshot(knowledge_documents(), CHUNKING)
    assert isinstance(snapshot, KnowledgeSnapshot), snapshot
    return snapshot


def group_of(chunk: KnowledgeChunk) -> str:
    """The content-equivalence group of a chunk: chunks of identical text are one group, whatever source declares them."""
    return hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()


def chunk_of(snapshot: KnowledgeSnapshot, document_key: str, paragraph: int) -> KnowledgeChunk:
    """The chunk that is paragraph ``paragraph`` of document ``document_key``: the chunk of that source whose text is that paragraph, exactly."""
    document = next(d for d in DOCUMENTS if d.key == document_key)
    matches = [c for c in snapshot.chunks if c.source_id == document.source_id and c.text == document.paragraphs[paragraph]]
    assert len(matches) == 1, (document_key, paragraph, len(matches))
    return matches[0]


def gold_groups(snapshot: KnowledgeSnapshot, query: FixtureQuery) -> frozenset[str]:
    return frozenset(group_of(chunk_of(snapshot, key, paragraph)) for key, paragraph in query.gold)


def gold_chunks(snapshot: KnowledgeSnapshot, query: FixtureQuery) -> tuple[KnowledgeChunk, ...]:
    """Every chunk of every gold group: the mirror's copy of a gold chunk is gold too."""
    groups = gold_groups(snapshot, query)
    return tuple(chunk for chunk in snapshot.chunks if group_of(chunk) in groups)


def fixture_digest() -> str:
    """The digest of everything that defines the benchmark: the corpus, the chunking, the stop list, the queries and their gold labels."""
    payload = {
        "version": BENCHMARK_VERSION,
        "kb_id": KB_ID,
        "chunking": CHUNKING.scheme_id,
        "stop_words": sorted(STOP_WORDS),
        "documents": [{"key": d.key, "source_id": d.source_id, "paragraphs": list(d.paragraphs)} for d in DOCUMENTS],
        "queries": [{"id": q.query_id, "split": q.split, "stratum": q.stratum, "text": q.text, "gold": [list(g) for g in q.gold]} for q in QUERIES],
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()
