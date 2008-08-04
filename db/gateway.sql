create table callbacks (
    service text not null,
    node text not null,
    uri text not null,
    PRIMARY KEY (service, node, uri)
);

