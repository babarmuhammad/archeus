-- 0006: conversation, intent and ideas (P7; p7-design-gate §4, domain-model §4, §6).
--
-- Same row shape as 0001-0005. A message's conversation and the message it
-- replies to are columns, so a thread and "the reply to this message" are
-- index lookups. `intents.message_id` is UNIQUE: one message is read once, so a
-- retried or re-delivered message can never produce a second intent (and so a
-- second mission). Ideas carry their machine's state as a column, like every
-- stateful entity.

CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    mission_id  TEXT REFERENCES missions (id),
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);

CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations (id),
    author          TEXT NOT NULL,
    in_reply_to     TEXT REFERENCES messages (id),
    version         INTEGER NOT NULL CHECK (version >= 1),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    created_by      TEXT NOT NULL,
    updated_by      TEXT NOT NULL,
    body            TEXT NOT NULL
);
CREATE INDEX messages_by_conversation ON messages (conversation_id);
CREATE INDEX messages_by_reply ON messages (in_reply_to);

CREATE TABLE intents (
    id          TEXT PRIMARY KEY,
    message_id  TEXT NOT NULL UNIQUE REFERENCES messages (id),
    kind        TEXT NOT NULL,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);

CREATE TABLE ideas (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    project_id   TEXT REFERENCES projects (id),
    state        TEXT NOT NULL,
    version      INTEGER NOT NULL CHECK (version >= 1),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    updated_by   TEXT NOT NULL,
    body         TEXT NOT NULL
);
