# Remote Sensing verification ledger

Every leaderboard containing a newly imported task-318 evaluation received a focused verify-evals audit. `PASS` means the retained rows are paper-native and comparable under the displayed contract after the listed cleanup.

| Benchmark | Dataset ID | Contract | Eval IDs audited | Verdict | Cleanup |
|---|---:|---|---|---|---|
| GEO-Bench | 876 | Six-task suite aggregates | 16928, 16929 | PASS | Set external-pretraining flags true |
| PANGEABench | 877 | Eight retained dense-task mean mIoU | 16935 | PASS | Set external-pretraining flag true |
| DIOR | 264 | Official HBB test, AP at IoU .5 | 16932, 17124, 17203 | PASS | None |
| DOTA v1.0 | 1475 | Official OBB test server; labeled SS/MS variants | 16936, 16957, 17002, 17183 | PASS | None |
| FAIR1M v1.0 | 1476 | Original 37-class v1.0 OBB test server | 16937, 17003 | PASS | Corrected dataset description to 15,266 images |
| HRSC2016 | 1477 | Official split; VOC07 11-point and VOC12 area AP separate | 16938, 16939 | PASS | None |
| DIOR-R | 1478 | Official rotated test; VOC07 11-point AP | 16958, 17004, 17125, 17184 | 3 PASS; 17125 FAIL | Deleted AeroGen YOLO-style mAP50 row 17125 and recalculated ranks |
| LoveDA | 272 | Official hidden test; seven-class macro mIoU | 16930, 16960, 17185 | PASS | Set DINOv3/LWGANet external-pretraining flags true |
| iSAID semantic validation | 1486 | 1,411/458 semantic split; 15-class macro mIoU | 16931, 16959, 17169 | PASS | Set DINOv3 external-pretraining flag true |
| ISPRS Potsdam | 1484 | RGB, no DSM, hidden 14-tile no-boundary test; five-class mIoU | 16990 | PASS | None |
| ISPRS Vaihingen | 1493 | IRRG, no DSM, hidden 17-tile no-boundary test; five-class mIoU | 16991 | PASS | Clarified methodology |
| LEVIR-CD | 1480 | Official 445/64/128 pairs; positive-class F1 | 16941, 16952, 17044, 17078, 17080, 17150, 17186 | PASS | Normalized Changen2 HF URL; fixed four external-pretraining flags |
| CDD season-varying | 1482 | Official 10k/3k/3k; positive-class F1 | 16940, 16955, 17045, 17188 | PASS | Fixed two external-pretraining flags |
| S2Looking | 1483 | Official 70/10/20 full side-looking test; positive-class F1 | 17046, 17079 | PASS | None |
| SYSU-CD | 1508 | Official 12k/4k/4k; positive-class F1 | 16934, 17082, 17189 | PASS | Fixed three external-pretraining flags |
| DSIFN-CD | 1510 | Five-city train/val and held-out Xi'an test; positive-class F1 | 16954, 17083 | PASS | Fixed CDMaskFormer external-pretraining flag |
| JL1-CD | 1512 | Official 4k/1k; per-image mean changed/unchanged F1 | 17064 | PASS | Canonicalized HF repository URL |
| WHU-CD BIT split | 1543 | 6,096/762/762 non-overlapping 256px patches | 17081 | PASS | Moved from mixed parent |
| WHU-CD geographic | 1544 | Geographic train/test areas; full-resolution test | 16933 | PASS in own setup | Moved from mixed parent |
| WHU-CD DDPM prepared | 1545 | Exact released DDPM-CD 256px lists | 16953 | PASS in own setup | Moved from mixed parent |
| WHU-CD LWGANet split | 1546 | Paper-specific 7,432-patch preparation | 17187 | PASS in own setup | Moved from mixed parent |
| RSICD image-to-text | 1500 | 1,093 image queries, 5,465 caption candidates, R@1 | 16961, 16994, 17204 | PASS | None |
| RSICD text-to-image | 1501 | 5,465 caption queries, 1,093 image candidates, R@1 | 16962, 16995, 17205 | PASS | None |
| RSITMD image-to-text | 1505 | 452 image queries, 2,260 caption candidates, R@1 | 16963, 16996, 17206 | PASS | None |
| RSITMD text-to-image | 1506 | 2,260 caption queries, 452 image candidates, R@1 | 16964, 16997, 17207 | PASS | None |
| EuroSAT RGB fixed 60/20/20 | 1537 | Neumann/google-research RGB split | 17095, 17162 | PASS in own setup | Moved from mixed parent |
| EuroSAT multispectral 13-band | 1538 | Stratified 80/20 seed 42 | 17094 | PASS in own setup | Moved from mixed parent |
| EuroSAT zero-shot complete | 1539 | No label training; complete dataset | 16993 | PASS in own setup | Moved from mixed parent |
| AID RoMA fixed 50% | 1547 | Fixed tag-0 50/50, one linear-probe run | 17167 | PASS in own setup | Moved off ten-random-split leaderboard |
| UC Merced RoMA fixed 50% | 1548 | Fixed/unspecified 50/50 linear-probe manifest | 17168 | PASS in own setup | Moved off repeated-random-split leaderboard |

The original EuroSAT and WHU-CD rows are now metric-free parent containers. A canonical EuroSAT RGB class-wise 80/20 child (1536) was also created for future results. No incompatible rows remain mixed on those parents.
