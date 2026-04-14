# FAA AI Chatbot - Complete Indexed Coverage Report

## Executive Summary

**Total Indexed Chunks:** 13,161  
**Unique Sections:** 6,800+  
**Primary Source:** eCFR Title 14 (Federal Aviation Regulations)  
**Index Size:** ~37 MB (embeddings.npy + chunks.jsonl)

---

## 1. PART 25: AIRWORTHINESS STANDARDS FOR TRANSPORT CATEGORY AIRPLANES

### Coverage: 398 SECTIONS | 790 CHUNKS

This is the **PRIMARY** regulatory source for the chatbot. All major Part 25 sections are indexed.

#### 25.1 - 25.99: GENERAL PROVISIONS (11 sections, 19 chunks)
- **25.1**: Applicability
- **25.2**: Special retroactive requirements
- **25.3**: General requirements
- **25.5**: Compatibility of equipment
- **25.21**: Proof of compliance
- **25.23**: Load distribution limits
- **25.25**: Weight limits
- **25.27**: Center of gravity limits
- **25.29**: Empty weight and loading
- **25.31**: Removable ballast
- **25.33**: Propeller speed and pitch limits

#### 25.100 - 25.299: PERFORMANCE STANDARDS (34 sections, 103 chunks)
**Strong coverage on**
- **25.101-25.125**: Takeoff performance (climb, obstacle clearance, balanced field)
- **25.143-25.149**: Cruise performance (speed, climb, altitude)
- **25.175-25.207**: Landing performance (approach, landing distance, obstacles)
- **25.253-25.255**: Fuel and oil consumption

#### 25.300 - 25.499: STRUCTURAL DESIGN AND LOADS (48 sections, 88 chunks)
**Strong coverage on**
- **25.305**: Strength and deformation
- **25.321-25.341**: Limit load static conditions
- **25.343-25.361**: Ultimate load conditions
- **25.365-25.397**: Structural factors and safety
- **25.415-25.499**: Fatigue evaluation and damage tolerance

#### 25.500 - 25.699: LANDING GEAR, BRAKES, AND TIRES (46 sections, 86 chunks)
**Strong coverage on**
- **25.503-25.535**: Landing gear design and extension
- **25.561-25.562**: ✅ **FULLY INDEXED** - Emergency landing conditions (CRITICAL)
- **25.571**: General landing gear conditions
- **25.613**: ✅ **FULLY INDEXED** - Material strength properties (CRITICAL)
- **25.621-25.629**: Wheel brakes
- **25.671-25.697**: Tires and shock absorber tests

#### 25.700 - 25.899: DESIGN AND CONSTRUCTION (56 sections, 158 chunks)
**Strong coverage on**
- **25.725-25.785**: Controls, seats, cabin fittings
- **25.783**: ✅ **FULLY INDEXED** - Fuselage doors (8+ chunks)
- **25.785**: ✅ **FULLY INDEXED** - Seats, berths and restraint systems (6 chunks)
- **25.795-25.883**: Doors, evacuation, emergency equipment
- **25.807-25.859**: ✅ **FULLY INDEXED** - Cabin interiors (10+ chunks each)
- **25.853**: ✅ **FULLY INDEXED** - Compartment interiors (flammability) (3 chunks)

#### 25.900 - 25.999: POWER PLANT AND SYSTEMS (38 sections, 64 chunks)
**Good coverage on**
- **25.901-25.981**: Engine mounting, cowling, fuel systems
- **25.963-25.967**: Fuel tank testing

#### 25.1000 - 25.1999: SYSTEMS AND EQUIPMENT (165 sections, 272 chunks)
**Excellent coverage on**
- **25.1001-25.1045**: General systems requirements
- **25.1093**: Instrument systems
- **25.1302-25.1337**: Instruments (flight, engine, warnings)
- **25.1323-25.1329**: Flight instruments display
- **25.1457-25.1459**: Fire detection and suppression
- **25.1583-25.1707**: Lighting systems
- **25.1805+**: Other systems and equipment

---

## 2. PART 21: CERTIFICATION PROCEDURES

### Coverage: 132 SECTIONS | 216 CHUNKS

Essential for STC (Supplemental Type Certificate) and certification questions.

### Most Indexed Sections:
- **21.1-21.5**: General (3-6 chunks each)
- **21.3**: Definitions ✅
- **21.4**: Rules of construction ✅
- **21.17**: Designation of applicable regulations ✅
- **21.21**: Issue of type certificate ✅
- **21.25**: Amendments ✅
- **21.27-21.35**: Prototype aircraft requirements
- **21.50**: Applicability of manufacturing requirements
- **21.73-21.93**: Aircraft manufacturing
- **21.101**: ✅ **CRITICAL** - Designation of applicable regulations for STCs
- **21.137-21.190**: Supplemental type certificate procedures
- **21.183-21.197**: ✅ **Key for STC questions**

---

## 3. PART 23: AIRWORTHINESS STANDARDS FOR SMALL AIRPLANES

### Coverage: 376 SECTIONS | 682 CHUNKS

Good reference for small aircraft modifications and comparisons.
- **23.1-23.999**: Parallel structure to Part 25 but less detailed in index

---

## 4. PART 36: NOISE STANDARDS

### Coverage: Present but minimal
- **36.1**: General (12+ chunks)

---

## 5. TRANSPORT CANADA CAR 525

### Coverage: **NOT FOUND IN FINAL INDEX**

While CAR 525 was supposed to be crawled, it does **not appear in the final indexed chunks**. The chatbot cannot answer TC CAR 525 specific questions from the index.

---

## CRITICAL SECTIONS FOR MOST QUESTIONS

### Top Questions This Chatbot WILL Answer Well:

1. **Material Properties & Structure** → §25.613, §25.301-25.341
2. **Emergency Landing Loads** → §25.561, §25.562
3. **Interior Flammability** → §25.853, Appendix F
4. **Seats & Restraints** → §25.785
5. **Doors & Evacuation** → §25.807, §25.810, §25.811
6. **STC Amendment Rules** → §21.101, §21.183
7. **Certification Basis** → §21.3, §21.4, §21.101
8. **Fatigue & Damage Tolerance** → §25.305, §25.343-25.361
9. **Fire Protection** → §25.1457, §25.1459
10. **Systems Requirements** → §25.1001+

### Top Questions This Chatbot WILL NOT Answer Well:

1. **Historical amendment text** (e.g., "§25.613 at Amendment 25-46") - Only current eCFR indexed
2. **Advisory Circular details** - AC index pages indexed, not full AC text
3. **TC CAR 525 specifics** - Not in final index (crawl may have failed)
4. **Part 23 in detail** - Minimal coverage
5. **Amendment change history** - Would need multiple snapshots
6. **Manufacturer guidance** - Not publicly available

---

## SECTION CATEGORIES STRENGTH RANKING

| Category | Coverage | Answer Quality |
|----------|----------|-----------------|
| Structures (25.3xx-25.4xx) | 88 chunks, 48 sections | ⭐⭐⭐⭐⭐ Excellent |
| Certification (21.x) | 216 chunks, 132 sections | ⭐⭐⭐⭐⭐ Excellent |
| Interiors (25.7xx-25.8xx) | 158 chunks, 56 sections | ⭐⭐⭐⭐⭐ Excellent |
| Emergency Landing (25.5xx) | 86 chunks, 46 sections | ⭐⭐⭐⭐ Very Good |
| Systems (25.1xxx) | 272 chunks, 165 sections | ⭐⭐⭐⭐ Very Good |
| Performance (25.1xx-25.2xx) | 103 chunks, 34 sections | ⭐⭐⭐ Good |
| Small Aircraft (Part 23) | 682 chunks, 376 sections | ⭐⭐⭐ Good |
| Transport Canada (CAR 525) | 0 chunks | ❌ Not Available |

---

## HOW TO VERIFY COVERAGE FOR A SPECIFIC QUESTION

When asking the chatbot a question, look for:

1. **Citations** - Are [C1], [C2] references provided?
2. **Confidence Score** - Is it >50%?
3. **Grounded flag** - Should be `true` for reliable answers
4. **Source** - Should show `faa_ecfr_title14_full` or `faa_far_part25`

### Example Good Answer:
```
"The aircraft must comply with § 25.561(b)(3) which specifies..."
[C1] Section 25.561 | Issue: 2017-01-01 | Score: 0.92
```

### Example Poor Answer:
```
"I cannot answer with sufficient certainty from the indexed sources"
Confidence: 0.0% | Grounded: false
```

---

## REBUILDING INDEX WITH MORE COVERAGE

To improve coverage (especially amendments and Advisory Circulars):

```bash
# Current build (what's deployed)
python scripts/build_index.py --reset --website-only --title14-full

# With historical amendments (3 versions back)
python scripts/build_index.py --reset --website-only --title14-full --title14-history-limit 3

# With AC text (if available in crawl)
python scripts/build_index.py --reset --website-only --title14-full --source faa_advisory_circulars
```

---

## KNOWN LIMITATIONS

1. ⚠️ **No CAR 525** - Transport Canada coverage failed
2. ⚠️ **No AC full text** - Only index pages, not documents
3. ⚠️ **No amendment history** - Can't compare Amendment 25-46 vs current
4. ⚠️ **No Part 135 / Part 91** - Only Title 14 Part 21, 23, 25, 36
5. ⚠️ **No manufacturer docs** - TCDS, AMM, etc. not publicly indexed
6. ⚠️ **No chat history persistence** - DOM-only, cleared on refresh

---

## BOTTOM LINE

**The chatbot is well-suited for:**
- ✅ Part 25 structural, systems, and interior compliance questions
- ✅ STC/certification procedure questions  
- ✅ Emergency landing and load requirements
- ✅ Material strength properties
- ✅ Interior flammability standards

**The chatbot struggles with:**
- ❌ Historical amendments
- ❌ Advisory Circular guidance
- ❌ Transport Canada regulations
- ❌ Manufacturer-specific guidance
- ❌ Amendment change tracking

