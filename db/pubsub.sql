create table entities (
    id serial primary key,
    jid text not null unique
);

create table nodes (
    id serial primary key,
    node text not null unique,
    persistent boolean not null default true,
    deliver_payload boolean not null default true,
    send_last_published_item text not null default 'on_sub'
        check (send_last_published_item in ('never', 'on_sub'))
);

create table affiliations (
    id serial primary key,
    entity_id integer not null references entities on delete cascade,
    node_id integer not null references nodes on delete cascade,
    affiliation text not null
        check (affiliation in ('outcast', 'publisher', 'owner')),
    unique (entity_id, node_id)
);

create table subscriptions (
    id serial primary key,
    entity_id integer not null references entities on delete cascade,
    resource text,
    node_id integer not null references nodes on delete cascade,
    subscription text not null default 'subscribed' check
        (subscription in ('subscribed', 'pending', 'unconfigured')),
    unique (entity_id, resource, node_id)
);

create table items (
    id serial primary key,
    node_id integer not null references nodes on delete cascade,
    item text not null,
    publisher text not null,
    data text,
    date timestamp with time zone not null default now(),
    unique (node_id, item)
);
