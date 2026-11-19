--
-- PostgreSQL database dump
--

\restrict pwaJdvVDLiW7DFhscaYTTOIorFjFgihVRAhwNmlGQ8vyCJ5Fh6QWLQMhbGJMWA1

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg12+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg12+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: cards; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cards (
    id integer NOT NULL,
    hand_id integer NOT NULL,
    rank character varying(2) NOT NULL,
    suit character varying(1) NOT NULL,
    order_no integer NOT NULL,
    CONSTRAINT ck_cards_order CHECK ((order_no > 0))
);


--
-- Name: cards_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cards_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cards_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cards_id_seq OWNED BY public.cards.id;


--
-- Name: hands; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hands (
    id integer NOT NULL,
    round_id integer NOT NULL,
    owner character varying(10) NOT NULL,
    score integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_hands_owner CHECK (((owner)::text = ANY ((ARRAY['player'::character varying, 'dealer'::character varying])::text[]))),
    CONSTRAINT ck_hands_score CHECK ((score >= 0))
);


--
-- Name: hands_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.hands_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: hands_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.hands_id_seq OWNED BY public.hands.id;


--
-- Name: players; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.players (
    id integer NOT NULL,
    nickname character varying(32) NOT NULL,
    password_hash character varying(255) NOT NULL,
    balance integer DEFAULT 1000 NOT NULL,
    rounds_played integer DEFAULT 0 NOT NULL,
    is_admin boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_players_balance CHECK ((balance >= 0)),
    CONSTRAINT ck_players_rounds_played CHECK ((rounds_played >= 0))
);


--
-- Name: players_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.players_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: players_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.players_id_seq OWNED BY public.players.id;


--
-- Name: rounds; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rounds (
    id integer NOT NULL,
    player_id integer NOT NULL,
    bet integer NOT NULL,
    status character varying(32) DEFAULT 'in_progress'::character varying NOT NULL,
    payout integer DEFAULT 0 NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    CONSTRAINT ck_rounds_bet CHECK (((bet > 0) AND ((bet % 2) = 0))),
    CONSTRAINT ck_rounds_payout CHECK ((payout >= 0)),
    CONSTRAINT ck_rounds_status CHECK (((status)::text = ANY ((ARRAY['in_progress'::character varying, 'player_won'::character varying, 'dealer_won'::character varying, 'push'::character varying, 'player_blackjack'::character varying, 'player_bust'::character varying, 'dealer_bust'::character varying])::text[])))
);


--
-- Name: rounds_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rounds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rounds_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rounds_id_seq OWNED BY public.rounds.id;


--
-- Name: cards id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cards ALTER COLUMN id SET DEFAULT nextval('public.cards_id_seq'::regclass);


--
-- Name: hands id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hands ALTER COLUMN id SET DEFAULT nextval('public.hands_id_seq'::regclass);


--
-- Name: players id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.players ALTER COLUMN id SET DEFAULT nextval('public.players_id_seq'::regclass);


--
-- Name: rounds id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rounds ALTER COLUMN id SET DEFAULT nextval('public.rounds_id_seq'::regclass);


--
-- Name: cards cards_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cards
    ADD CONSTRAINT cards_pkey PRIMARY KEY (id);


--
-- Name: hands hands_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hands
    ADD CONSTRAINT hands_pkey PRIMARY KEY (id);


--
-- Name: players players_nickname_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.players
    ADD CONSTRAINT players_nickname_key UNIQUE (nickname);


--
-- Name: players players_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.players
    ADD CONSTRAINT players_pkey PRIMARY KEY (id);


--
-- Name: rounds rounds_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rounds
    ADD CONSTRAINT rounds_pkey PRIMARY KEY (id);


--
-- Name: cards uq_cards_hand_card; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cards
    ADD CONSTRAINT uq_cards_hand_card UNIQUE (hand_id, rank, suit);


--
-- Name: cards uq_cards_hand_order; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cards
    ADD CONSTRAINT uq_cards_hand_order UNIQUE (hand_id, order_no);


--
-- Name: hands uq_hands_round_owner; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hands
    ADD CONSTRAINT uq_hands_round_owner UNIQUE (round_id, owner);


--
-- Name: ix_rounds_player_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rounds_player_id ON public.rounds USING btree (player_id);


--
-- Name: cards cards_hand_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cards
    ADD CONSTRAINT cards_hand_id_fkey FOREIGN KEY (hand_id) REFERENCES public.hands(id) ON DELETE CASCADE;


--
-- Name: hands hands_round_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hands
    ADD CONSTRAINT hands_round_id_fkey FOREIGN KEY (round_id) REFERENCES public.rounds(id) ON DELETE CASCADE;


--
-- Name: rounds rounds_player_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rounds
    ADD CONSTRAINT rounds_player_id_fkey FOREIGN KEY (player_id) REFERENCES public.players(id);


--
-- PostgreSQL database dump complete
--

\unrestrict pwaJdvVDLiW7DFhscaYTTOIorFjFgihVRAhwNmlGQ8vyCJ5Fh6QWLQMhbGJMWA1

