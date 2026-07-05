pragma foreign_keys = on;

create table if not exists documents (
    document_id text primary key,
    title text not null,
    year integer not null,
    study_design text not null,
    source_type text not null,
    publication_status text not null,
    abstract text not null default '',
    journal text not null,
    doi text,
    pmid text,
    is_preprint integer not null default 0,
    is_retracted integer not null default 0,
    funding text,
    conflicts text,
    population text,
    intervention text,
    comparator text,
    outcomes_json text not null default '[]'
);

create table if not exists passages (
    passage_id text primary key,
    document_id text not null references documents(document_id),
    section text not null,
    text text not null,
    page integer,
    table_id text
);

create table if not exists evidence_profiles (
    document_id text primary key references documents(document_id),
    study_design text not null,
    evidence_level text not null,
    bias_flags_json text not null default '[]',
    applicability_flags_json text not null default '[]',
    retraction_status text not null,
    preprint_status integer not null default 0,
    assessment_confidence real not null,
    funding text,
    conflicts text,
    missing_information_warnings_json text not null default '[]'
);

create table if not exists citations (
    citation_id text primary key,
    document_id text not null references documents(document_id),
    passage_id text not null references passages(passage_id),
    claim text not null,
    supports_claim integer not null
);

create table if not exists golden_questions (
    question_id text primary key,
    question text not null,
    category text not null,
    expected_action text not null
);

create table if not exists expected_documents (
    question_id text not null references golden_questions(question_id),
    document_id text not null references documents(document_id),
    primary key (question_id, document_id)
);

create table if not exists expected_evidence_flags (
    question_id text not null references golden_questions(question_id),
    flag text not null,
    primary key (question_id, flag)
);

create table if not exists research_memory (
    memory_id text primary key,
    tenant_id text not null,
    workspace_id text not null,
    user_id text not null,
    research_topic text not null,
    payload_json text not null,
    created_at text not null
);

create table if not exists audit_events (
    event_id text primary key,
    run_id text not null,
    event_type text not null,
    payload_json text not null,
    created_at text not null
);
