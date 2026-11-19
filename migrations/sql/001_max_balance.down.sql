SET LOCAL lock_timeout = '5s';

DROP TRIGGER blackjack_record_max_balance ON public.players;
DROP FUNCTION public.blackjack_record_max_balance();
ALTER TABLE public.players DROP COLUMN max_balance;
