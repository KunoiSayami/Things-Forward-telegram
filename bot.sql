--
-- PostgreSQL database dump
--

-- Dumped from database version 12.4
-- Dumped by pg_dump version 12.4

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

--
-- Name: fwd_target; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.fwd_target AS ENUM (
    'other',
    'photo',
    'bot',
    'video',
    'anime',
    'gif',
    'doc',
    'lowq'
);


ALTER TYPE public.fwd_target OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: blacklist; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.blacklist (
    id bigint NOT NULL
);


ALTER TABLE public.blacklist OWNER TO postgres;

--
-- Name: file_id; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.file_id (
    id character varying(80) NOT NULL,
    "timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.file_id OWNER TO postgres;

--
-- Name: msg_detail; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.msg_detail (
    id bigint NOT NULL,
    to_chat bigint DEFAULT 0 NOT NULL,
    to_msg integer DEFAULT 0 NOT NULL,
    from_chat bigint NOT NULL,
    from_id bigint NOT NULL,
    from_user bigint NOT NULL,
    forward_from bigint
);


ALTER TABLE public.msg_detail OWNER TO postgres;

--
-- Name: msg_detail_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.msg_detail_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.msg_detail_id_seq OWNER TO postgres;

--
-- Name: msg_detail_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.msg_detail_id_seq OWNED BY public.msg_detail.id;


--
-- Name: special_forward; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.special_forward (
    chat_id bigint NOT NULL,
    target public.fwd_target NOT NULL
);


ALTER TABLE public.special_forward OWNER TO postgres;

--
-- Name: user_list; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_list (
    id bigint NOT NULL,
    authorized boolean DEFAULT false NOT NULL,
    bypass boolean DEFAULT false NOT NULL,
    is_blacklist boolean DEFAULT false NOT NULL
);


ALTER TABLE public.user_list OWNER TO postgres;

--
-- Name: msg_detail id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.msg_detail ALTER COLUMN id SET DEFAULT nextval('public.msg_detail_id_seq'::regclass);


--
-- Name: blacklist blacklist_pk; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.blacklist
    ADD CONSTRAINT blacklist_pk PRIMARY KEY (id);


--
-- Name: file_id file_id_pk; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.file_id
    ADD CONSTRAINT file_id_pk PRIMARY KEY (id);


--
-- Name: msg_detail msg_detail_pk; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.msg_detail
    ADD CONSTRAINT msg_detail_pk PRIMARY KEY (id);


--
-- Name: special_forward special_forward_pk; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.special_forward
    ADD CONSTRAINT special_forward_pk PRIMARY KEY (chat_id);


--
-- PostgreSQL database dump complete
--

