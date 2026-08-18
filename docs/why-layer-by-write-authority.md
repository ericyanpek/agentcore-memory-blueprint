# Why Layer by Write Authority

> Chinese is the primary version: **[为什么按写入权威分层.md](为什么按写入权威分层.md)**.
> This document names no platform. The argument holds on any system with layered memory.

This document makes one argument: memory layers should be divided by who is entitled to
change a layer, not by what a layer contains. Deployment shape and storage choices are out
of scope — one concrete implementation is in [architecture.md](architecture.md), and the
external evidence behind each trade-off is in [design-rationale.md](design-rationale.md).

## The problem: episodic/semantic cannot answer the only question that matters

The conventional taxonomy divides memory by **the form of its content**: episodic is what
happened, semantic is the facts abstracted from it, procedural is how to do something. The
vocabulary comes from cognitive psychology, and as descriptive language it works.

But the question a running system answers every day is not "which category is this memory," it
is **"may this one override that one."** A user said last week they prefer one definition of a
metric; a team document specifies another; they conflict; pick.

A containment taxonomy has nothing to say here. There is no function from type to authority:
an episodic memory may be a reviewed conclusion from an incident post-mortem, and a semantic
memory may be a guess a model extracted from small talk. Grouping by type puts the two
records with the widest authority gap into the same bucket.

"May this be deleted," "who is affected if it is," and "who is accountable when it is wrong"
go equally unanswered — and those three are the same question as overriding, asked
differently. Each turns on **who wrote it**. The natural axis for layering is the writer.

## Six layers and who writes them

| Layer | Writer | Directly retrievable by the agent | Cost of change |
|---|---|---|---|
| Logs (observability) | Appended by the system | No | Immutable; only expires |
| Short-term memory (raw interaction) | The session itself | Current session only | Dies with the session |
| Personal long-term memory (extracted) | The extraction model | Yes, owner only | One turn of dialogue |
| Shared long-term memory (reviewed) | A human reviewer | Yes, to the team | One proposal, one approval |
| Knowledge Base (document owners) | Document owners | Yes | Document revision process |
| Skills (version-control review) | Review and tests | Loaded by trigger condition | Commit, review, merge |

Each row has exactly one class of writer, and that is the whole requirement. The layering
does not demand that content be disjoint, only that **write permission** be disjoint. The
same fact appearing in both a personal preference and an authoritative document is not a
problem; one principal being able to write both the personal and the shared layer is.

The "cost of change" column is not an aside but the same property measured another way. A
layer that is harder to change is more trustworthy, not because its content is better, but
because it is harder to alter unilaterally. The six are ordered neither by recency nor by
specificity, but by how many people a change must pass through.

## Conflict resolution becomes a table lookup

Because each layer has exactly one class of writer, "which one wins" collapses into "which
layers are they in." That is a lookup, not a judgment: it can be settled before retrieval,
without reading the text of either memory, and with no model in the path.

The rejected alternative is to hand both contradicting memories to a model and let it decide
at retrieval time which to believe. In comparable systems this is the weakest link, and it is
weak because of the design rather than the implementation quality:

- It makes correctness depend on an inference that is itself unreliable. The step that most
  needs to be certain has been swapped for the least certain one.
- It is unauditable. The same two inputs need not produce the same ruling twice, so
  explaining afterwards why a record was used means rerunning it — and a rerun is not
  guaranteed to reproduce.

The price should be stated too: a lookup cannot resolve a contradiction *within* a layer.
When two reviewed team memories conflict, layer order gives no answer. That needs an explicit
supersession relation, where a person names which record is void rather than letting a
similarity score decide. Layering reduces how often human adjudication is needed; it does not
remove it.

## Retrieval precedence must be a total order

A partial order is not enough. It means some layers are mutually incomparable, and
"incomparable" does not stay honestly undefined in an implementation — it gets quietly
settled by some default, and that default is almost always the similarity score.

Similarity measures topical relevance. It measures neither authority nor recency. A stale
preference from two years ago will outrank a document updated yesterday so long as its
wording sits closer to the question. That is not a defect in the retrieval implementation; it
is what similarity means — a memory is retrieved precisely *because* it resembles the query.

So precedence must be a total order, and it must be handed to the model along with the
context rather than living only in a design document:

live data > Skills > authoritative documents > reviewed team memory > personal preference

The last term needs one further constraint: **personal preference may affect presentation
only, never substance.** A user who prefers a unit, a phrasing, or an output format gets it;
a user who prefers a number does not. Without this the personal layer becomes a bypass
around every layer above it — and it is exactly the layer that is easiest to write and least
reviewed.

This total order replaces "which memories are relevant" with "which authority wins." The
first question has no determinate answer. The second does.

## The shared tier is a staging area for knowledge assets

Only one of the six layers is new: reviewed shared memory. It exists to fill a real gap — an
experience has proven useful, but does not yet justify writing a document for it.

It sits deliberately between its two neighbours: more governed than an openly writable vector
store (attributed, reviewed, backed by an evidence reference, revocable), and lower friction
than authoring a document (one proposal and one approval, not a document review). Landing the
friction in between is the precondition for it being used at all — govern it more and nobody
proposes, govern it less and it decays into an unowned pool of memories.

"Staging area" means **its contents are supposed to leave.** A shared memory used repeatedly,
with stable wording, should be promoted — declarative ones into documents, operational ones
into executable procedures; once promoted, its copy in the shared tier should be retired.

Promotion is a manual act. No automatic mechanism can judge whether an experience has
stabilised enough to be written into a document, and this document does not pretend otherwise.
What the system can do is put the evidence on the table: how often the record was retrieved,
which answers used it, how long ago it last changed.

A staging area whose contents never graduate has already failed. It grows into a store better
governed but just as bloated, when its purpose was to be a transit point. The only indicator
of whether it works is whether promotion has ever happened.

## What this layering does not promise

This is the section that matters most, because the previous five hold only inside the
boundary drawn here.

**It does not improve answer quality.** Layering does not make a model answer more
accurately. Putting a memory into a governed layer adds nothing to that memory's
correctness; it only makes it knowable who put it there.

**It is not measured against QA accuracy.** The argument does not rest on any
question-answering benchmark number, because those numbers measure something else. Published
memory benchmarks have documented methodological problems — answer-key errors, judges that
accept topically adjacent but wrong answers, and corpora that fit whole into a context window,
making them context-window tests rather than memory tests. Using them to show that governance
works is supporting a conclusion with evidence that cannot carry it.

**It does not deduplicate.** Layering does not merge semantically redundant memories, detect
contradictions within a layer, or clean up stale content. Those are separate problems needing
separate mechanisms.

So what is its objective function? Three properties, all verifiable without measuring answer
quality at all:

- **Blast radius.** How far a poisoned or mistaken memory can reach. An error in the personal
  layer stops at one person; an error in the shared layer stops at one team, and necessarily
  passed through an attributed review action.
- **Attributability.** For any memory that was used, being able to answer who wrote it, on
  what evidence, and when.
- **Revocability.** Once a record is found to be wrong, being able to locate it, void it, and
  know which past answers it influenced.

These three are not proxies for answer quality and should not be used as such. A system with
a small blast radius, full attribution, and revocation on demand can still answer badly. The
argument in this document promises no remedy for that.
