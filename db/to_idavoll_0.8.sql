ALTER TABLE affiliations RENAME id TO affiliation_id;

ALTER TABLE entities RENAME id TO entity_id;

ALTER TABLE items RENAME id TO item_id;

ALTER TABLE nodes RENAME id TO node_id;
ALTER TABLE nodes RENAME persistent to persist_items;
ALTER TABLE nodes RENAME deliver_payload to deliver_payloads;
ALTER TABLE nodes ADD COLUMN node_type text;
ALTER TABLE nodes ALTER COLUMN node_type SET DEFAULT 'leaf';
UPDATE nodes SET node_type = 'leaf';
ALTER TABLE nodes ALTER COLUMN node_type SET NOT NULL;
ALTER TABLE nodes ADD CHECK (node_type IN ('leaf', 'collection'));
ALTER TABLE nodes ALTER COLUMN persistent DROP NOT NULL;
ALTER TABLE nodes ALTER COLUMN persistent DROP DEFAULT;

ALTER TABLE subscriptions RENAME id TO subscription_id;
ALTER TABLE subscriptions RENAME subscription TO state;
ALTER TABLE subscriptions ADD COLUMN subscription_type text
    	CHECK (subscription_type IN (NULL, 'items', 'nodes'));
ALTER TABLE subscriptions ADD COLUMN subscription_depth text
    	CHECK (subscription_depth IN (NULL, '1', 'all'));

INSERT INTO nodes (node, node_type) values ('', 'collection');
