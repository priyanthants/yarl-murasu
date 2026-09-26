CREATE TABLE IF NOT EXISTS push_subscriptions (
  endpoint TEXT PRIMARY KEY,
  login TEXT NOT NULL,
  subscription_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS push_subscriptions_login ON push_subscriptions(login);

CREATE TABLE IF NOT EXISTS notified_stories (
  story_id TEXT PRIMARY KEY,
  notified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
