ALTER TABLE assignments ADD COLUMN github_owner TEXT;
ALTER TABLE assignments ADD COLUMN github_repo TEXT
    CHECK ((github_owner IS NULL) = (github_repo IS NULL));
