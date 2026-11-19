SET LOCAL lock_timeout = '5s';

ALTER TABLE public.players ADD COLUMN max_balance integer;

UPDATE public.players
SET max_balance = balance
WHERE max_balance IS NULL;

ALTER TABLE public.players
    ALTER COLUMN max_balance SET DEFAULT 1000,
    ALTER COLUMN max_balance SET NOT NULL,
    ADD CONSTRAINT ck_players_max_balance CHECK (max_balance >= balance);

CREATE FUNCTION public.blackjack_record_max_balance() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO pg_catalog
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.max_balance := NEW.balance;
    ELSE
        NEW.max_balance := GREATEST(OLD.max_balance, NEW.balance);
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER blackjack_record_max_balance
    BEFORE INSERT OR UPDATE OF balance ON public.players
    FOR EACH ROW EXECUTE FUNCTION public.blackjack_record_max_balance();
