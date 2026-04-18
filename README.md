# Solving(?) Ghost

This is a repository for the page at ... with a few scripts for generating those DAGs, a word list, and a _Ghost_ bot that will give you possible winning/losing moves for a given fragment.

## How to play Ghost 
Ghost is a two-player word game where players take turns adding one letter to the end of a growing fragment, trying not to be the player who completes a valid word of four or more letters; for example, if the fragment is _TRE_, playing _E_ makes _TREE_, so that player loses. Each fragment must also be extendable into some valid dictionary word, so if one player makes a fragment like _GHX_ and no word starts that way, the other player can challenge and win. Short words under four letters do not count as losing completed words, so making _AN_ or _BAR_ is safe as long as the fragment can still be extended. A sample round might go _T_, _R_, _E_; now the next player should avoid _E_ because tree loses, and might play another letter only if the dictionary has a longer word beginning with that new fragment (perhaps they'd like to play _W_ and force the other player to spell [_TREWS_](https://en.wikipedia.org/wiki/Trews)).

I don't remember if this game was called _Ghost_ or _Ghost of Three Thirds_ or something else like that, but when I was in Taiwan, I spent a lot of time playing it with a friend. We actually got into a really big argument about whether 'drear' was a word (after I played _R_ to the current _DREA_).

I forgot what my friend actually called the game and I'm too lazy right now to text her as I write this README, so I'll just be calling it _Ghost_ here.

## What this repo is

I generated two DAGS to show: (a) how one can win if they go first and play perfectly, or (b) how one can win if they go second and their opponent played imperfectly on the first play.

`words.txt` is generated using [SCOWL](https://github.com/en-wl/wordlist). The list was made like so:
```bash
make -C third_party/wordlist
python tools/build_ghost_dictionary.py --output words.txt --summary
```

It converts the list into the format ghost_bot.py wants:
- one word per line
- ASCII only
- alphabetic only
- length 4 or more
- deduplicated
- and sorted.

It also rejects capitalized or mixed-case SCOWL source entries by default. That matters because SCOWL includes entries like Monday, September, or Easter. If we simply lowercased everything, those would become playable Ghost words. The script avoids that by only accepting source words that are already lowercase, unless `--keep-capitalized` is passed. The size (60) passed in as an argument to SCOWL also prevents really big, obnoxious words like _TRANSUBSTANTIATIONIST_ or _ANTIDISESTABLISHMENTARIANISM_.


## _Ghost_ Bot
You can play `ghost_bot.py` with 
```bash
python3 ghost_bot.py --dict words.txt --interactive
```
but, it's not very fun since _Ghost_ Bot knows every word in the English dictionary and can see every path into the future. Especially since the game is solved easily (at least for this word list).

Running this:
```bash
python3 ghost_bot.py --dict words.txt
```
you get
```
Status: winning position
Best action: play 'j'
Reason: adding 'j' leaves "j" as a losing position for the opponent; all opponent responses eventually lose with perfect play
Winning moves: h (6 plies), j (4 plies), m (8 plies), r (10 plies)
Losing moves: a (9 plies), b (5 plies), c (5 plies), d (5 plies), e (7 plies), f (5 plies), g (5 plies), i (7 plies), k (5 plies), l (5 plies), n (5 plies), o (5 plies), p (5 plies), q (5 plies), s (5 plies), t (5 plies), u (7 plies), v (5 plies), w (5 plies), x (11 plies), y (7 plies), z (5 plies)
```

Pretty interesting. I plotted out the possible winning moves for _H_, _J_, _M_, and _R_ in the GitHub page and the winning moves for the second player if the first player doesn't pick any of those four letters.