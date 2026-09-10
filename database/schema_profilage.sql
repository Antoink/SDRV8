-- ===========================================================================
-- Schéma PostgreSQL pour l'app de profilage SDR (v2 — schéma flexible)
-- ===========================================================================
-- Trois tables :
--   joueurs : une ligne par joueur (identité, ne change presque jamais)
--   sessions : une ligne par (joueur, session de tests)
--   mesures  : une ligne par (session, test) -- flexible : "nom_test" est
--              le nom de colonne Excel/Google Sheet tel quel (ex "CMJ 2JB").
--
-- Règle simple : seule l'identité du joueur a des colonnes SQL fixes.
-- Absolument tout le reste (âge, poids, et tous les tests physiques/
-- physiologiques/ISAK/1080 Sprint) est stocké comme des lignes dans
-- `mesures`. Ajouter un nouveau test = juste ajouter une colonne dans le
-- Google Sheet puis relancer database/sync_from_google_sheets.py -- aucune
-- modification de ce schéma n'est nécessaire.
-- ===========================================================================

-- -----------------------------------------------------------------------
-- Table 1 : joueurs (identité)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS joueurs (
    id                SERIAL PRIMARY KEY,
    nom               TEXT NOT NULL UNIQUE,  -- ex: "AKIEME Sergio" (colonne "Joueur")
    n_gps             TEXT,
    lateralite        TEXT,
    poste             TEXT,
    position          TEXT,
    date_de_naissance DATE,
    equipe            TEXT
);

-- -----------------------------------------------------------------------
-- Table 2 : sessions (une ligne = un joueur + une session de tests)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id             SERIAL PRIMARY KEY,
    joueur_id      INTEGER NOT NULL REFERENCES joueurs(id) ON DELETE CASCADE,
    session_label  TEXT,   -- colonne "Session", ex "Pré-saison"
    session_date   DATE    -- colonne "Session exact"
);

-- Un joueur ne doit avoir qu'une seule session pour une date donnée
-- (COALESCE sert à gérer le cas où la date de session est vide)
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_joueur_date
    ON sessions (joueur_id, COALESCE(session_date, '0001-01-01'::date));

-- -----------------------------------------------------------------------
-- Table 3 : mesures (flexible -- une ligne par test passé lors d'une session)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mesures (
    id            SERIAL PRIMARY KEY,
    session_id    INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    nom_test      TEXT NOT NULL,      -- nom de colonne Excel/Sheet d'origine
    valeur_num    DOUBLE PRECISION,   -- rempli si la valeur est un nombre
    valeur_texte  TEXT                -- rempli sinon (texte brut)
);

-- Un test donné n'apparaît qu'une fois par session
CREATE UNIQUE INDEX IF NOT EXISTS idx_mesures_session_test
    ON mesures (session_id, nom_test);

CREATE INDEX IF NOT EXISTS idx_mesures_session_id ON mesures (session_id);
CREATE INDEX IF NOT EXISTS idx_mesures_nom_test ON mesures (nom_test);
