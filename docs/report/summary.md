# UNIFORM vs FAST summary

Two-sided Mann-Whitney U (alpha 0.05); A12 is A12(FAST, UNIFORM): > 0.5 means FAST's values tend to be larger, so smaller is better for TTFC. TTFC is right-censored at the budget (a first crash after it counts as not found); '> budget' is a quantile not reached; 'not determinable (>= half not reached)' means exactly half of an even-sized arm is censored; 'not determinable (interpolates a not-reached trial)' marks a quartile that falls between an observed time and a not-reached one. A cell starting '>= t' is a lower bound (t = the arm's largest observed time), not an estimate.

Primary family: m = 6 of 6, Holm-Bonferroni.

| target | metric | family | n (U/F) | median U [q1,q3] | median F [q1,q3] | find rate U / F | U | p | p_holm | significant | A12 | better | favours | low n |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mini_format | final_edges | primary | 10/10 | 45 [45, 46.75] | 45 [44.25, 46] |  | 45 | 0.7265 | 1 | False | 0.45 | larger | UNIFORM |  |
| mini_format | edges_auc | exploratory | 10/10 | 2.275e+04 [2.183e+04, 2.323e+04] | 2.346e+04 [2.126e+04, 2.51e+04] |  | 59 | 0.5205 exploratory (uncorrected) |  |  | 0.59 | larger | FAST |  |
| mini_format | unique_crashes | exploratory | 10/10 | 1 [0.25, 1] | 1 [1, 1] |  | 65 | 0.07672 exploratory (uncorrected) |  |  | 0.65 | larger | FAST |  |
| mini_format | ttfc:mfp-1 | primary | 10/10 | > budget [> budget, > budget] | > budget [> budget, > budget] | 0/10 / 0/10 | 50 | 1 | 1 | False | 0.5 | smaller | neither |  |
| mini_format | ttfc:mfp-2 | exploratory | 10/10 | 121 [15, >= 174.9 not determinable (interpolates a not-reached trial)] | 69.66 [15, 233.5] | 7/10 / 10/10 | 41 | 0.5199 exploratory (uncorrected) |  |  | 0.41 | smaller | FAST |  |
| tlv_parser | final_edges | primary | 10/10 | 13 [13, 13] | 13 [13, 13.75] |  | 57.5 | 0.5129 | 1 | False | 0.575 | larger | FAST |  |
| tlv_parser | edges_auc | exploratory | 10/10 | 7222 [7042, 7494] | 7434 [6753, 7676] |  | 56 | 0.6776 exploratory (uncorrected) |  |  | 0.56 | larger | FAST |  |
| tlv_parser | unique_crashes | exploratory | 10/10 | 1 [1, 2] | 1 [1, 1.75] |  | 45 | 0.6809 exploratory (uncorrected) |  |  | 0.45 | larger | UNIFORM |  |
| tlv_parser | ttfc:tlv-1 | exploratory | 10/10 | 0.1825 [0.1442, 0.2704] | 0.1956 [0.15, 0.2733] | 10/10 / 10/10 | 58 | 0.5708 exploratory (uncorrected) |  |  | 0.58 | smaller | UNIFORM |  |
| tlv_parser | ttfc:tlv-2 | primary | 10/10 | > budget [365.3, > budget] | > budget [>= 181.2 not determinable (interpolates a not-reached trial), > budget] | 4/10 / 3/10 | 52 | 0.8942 | 1 | False | 0.52 | smaller | UNIFORM |  |
| toy_parser | final_edges | primary | 10/10 | 7 [7, 8] | 7.5 [7, 8] |  | 55 | 0.6934 | 1 | False | 0.55 | larger | FAST |  |
| toy_parser | edges_auc | exploratory | 10/10 | 4166 [4097, 4190] | 4122 [4046, 4346] |  | 46 | 0.7913 exploratory (uncorrected) |  |  | 0.46 | larger | UNIFORM |  |
| toy_parser | unique_crashes | exploratory | 10/10 | 1 [1, 1] | 1 [1, 1] |  | 50 | 1 exploratory (uncorrected) |  |  | 0.5 | larger | neither |  |
| toy_parser | ttfc:toy-1 | primary | 10/10 | > budget [> budget, > budget] | > budget [> budget, > budget] | 1/10 / 1/10 | 49.5 | 1 | 1 | False | 0.495 | smaller | FAST |  |
| toy_parser | ttfc:toy-2 | exploratory | 10/10 | 9.717 [3.656, 12.41] | 9.726 [3.659, 12.42] | 10/10 / 10/10 | 52 | 0.9097 exploratory (uncorrected) |  |  | 0.52 | smaller | UNIFORM |  |

## Crash-site sentinel flags (main campaign)

none
