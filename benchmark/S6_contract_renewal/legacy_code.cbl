       IDENTIFICATION DIVISION.
       PROGRAM-ID. CONTRACT-RENEWAL-PROC.
       AUTHOR. LEGACY-TELECOM-SYSTEMS.
      *================================================================
      * CONTRACT RENEWAL PROCESSING SYSTEM
      * Handles contract renewals: eligibility check, discount
      * calculation, term adjustment, early termination fees,
      * and loyalty credits.
      *================================================================

       DATA DIVISION.
       WORKING-STORAGE SECTION.

       01  WS-CONTRACT-REQUEST.
           05  WS-CONTRACT-ID          PIC X(12).
           05  WS-ACTION               PIC X(5).
               88  ACT-RENEW           VALUE 'RENEW'.
               88  ACT-TERM            VALUE 'TERM'.
               88  ACT-QUERY           VALUE 'QUERY'.
               88  ACT-MODIFY          VALUE 'MOD'.
           05  WS-CUSTOMER-ID          PIC X(10).
           05  WS-CURRENT-TERM         PIC 9(2).
           05  WS-NEW-TERM             PIC 9(2).
               88  TERM-12             VALUE 12.
               88  TERM-24             VALUE 24.
               88  TERM-36             VALUE 36.
           05  WS-MONTHLY-RATE         PIC 9(7)V99.
           05  WS-ACCOUNT-TENURE-MO    PIC 9(4).
           05  WS-REMAINING-MONTHS     PIC 9(2).
           05  WS-SERVICES-COUNT       PIC 9(2).
           05  WS-BUNDLE-FLAG          PIC X(1).
               88  IS-BUNDLED           VALUE 'Y'.
               88  NOT-BUNDLED          VALUE 'N'.

       01  WS-CONTRACT-RECORD.
           05  WS-STATUS               PIC X(8).
               88  CSTAT-ACTIVE        VALUE 'ACTIVE'.
               88  CSTAT-EXPIRING      VALUE 'EXPIRING'.
               88  CSTAT-EXPIRED       VALUE 'EXPIRED'.
               88  CSTAT-TERMINATED    VALUE 'TERMINAT'.
           05  WS-AUTO-RENEW           PIC X(1).
               88  AUTO-RENEW-ON       VALUE 'Y'.
               88  AUTO-RENEW-OFF      VALUE 'N'.
           05  WS-LOYALTY-TIER         PIC X(4).
               88  LOYAL-PLAT          VALUE 'PLAT'.
               88  LOYAL-GOLD          VALUE 'GOLD'.
               88  LOYAL-SILV          VALUE 'SILV'.

       01  WS-RESULT-RECORD.
           05  WS-RESULT-CODE         PIC X(4).
           05  WS-NEW-RATE            PIC 9(7)V99.
           05  WS-DISCOUNT-PCT        PIC 9(3)V99.
           05  WS-ETF-AMOUNT          PIC 9(7)V99.
           05  WS-LOYALTY-CREDIT      PIC 9(5)V99.

       01  WS-LOYALTY-THRESHOLD-SILV PIC 9(4) VALUE 24.
       01  WS-LOYALTY-THRESHOLD-GOLD PIC 9(4) VALUE 60.
       01  WS-LOYALTY-THRESHOLD-PLAT PIC 9(4) VALUE 120.

       01  WS-12MO-DISCOUNT          PIC 9(3)V99 VALUE 5.00.
       01  WS-24MO-DISCOUNT          PIC 9(3)V99 VALUE 12.00.
       01  WS-36MO-DISCOUNT          PIC 9(3)V99 VALUE 20.00.

       01  WS-BUNDLE-EXTRA-DISCOUNT  PIC 9(3)V99 VALUE 5.00.
       01  WS-LOYALTY-CREDIT-PCT     PIC 9(3)V99 VALUE 2.00.

       01  WS-ETF-PER-MONTH          PIC 9(5)V99 VALUE 25.00.
       01  WS-ETF-MAX                PIC 9(7)V99 VALUE 500.00.

       01  WS-ERROR-CODE              PIC X(4).
       01  WS-STATUS-FLAG             PIC X(2).
           88  STATUS-OK              VALUE 'OK'.
           88  STATUS-ERR             VALUE 'ER'.

       PROCEDURE DIVISION.
       MAIN-PROCESS.
           PERFORM VALIDATE-CONTRACT-REQUEST
           IF STATUS-OK
               EVALUATE TRUE
                   WHEN ACT-RENEW
                       PERFORM RENEW-CONTRACT
                   WHEN ACT-TERM
                       PERFORM TERMINATE-CONTRACT
                   WHEN ACT-QUERY
                       PERFORM QUERY-CONTRACT
                   WHEN ACT-MODIFY
                       PERFORM MODIFY-CONTRACT
               END-EVALUATE
           END-IF
           STOP RUN.

      *================================================================
      * BR-001: Validate contract request
      *================================================================
       VALIDATE-CONTRACT-REQUEST.
           IF WS-CONTRACT-ID = SPACES
               MOVE 'R001' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF WS-ACTION = SPACES
               MOVE 'R002' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF NOT (ACT-RENEW OR ACT-TERM
                        OR ACT-QUERY OR ACT-MODIFY)
               MOVE 'R002' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF ACT-RENEW AND WS-CUSTOMER-ID = SPACES
               MOVE 'R003' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF ACT-RENEW AND
                   NOT (TERM-12 OR TERM-24 OR TERM-36)
               MOVE 'R004' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE
               SET STATUS-OK TO TRUE
           END-IF.

      *================================================================
      * BR-002: Renewal eligibility check
      * BR-003: Term-based discount calculation
      * BR-004: Bundle discount
      *================================================================
       RENEW-CONTRACT.
      *    Only ACTIVE or EXPIRING contracts can be renewed
           IF NOT (CSTAT-ACTIVE OR CSTAT-EXPIRING)
               MOVE 'R005' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

           IF STATUS-OK
      *        Calculate base discount by new term
               EVALUATE TRUE
                   WHEN TERM-12
                       MOVE WS-12MO-DISCOUNT TO WS-DISCOUNT-PCT
                   WHEN TERM-24
                       MOVE WS-24MO-DISCOUNT TO WS-DISCOUNT-PCT
                   WHEN TERM-36
                       MOVE WS-36MO-DISCOUNT TO WS-DISCOUNT-PCT
               END-EVALUATE

      *        IMPLICIT: Bundle discount stacks with term discount
               IF IS-BUNDLED AND WS-SERVICES-COUNT >= 3
                   ADD WS-BUNDLE-EXTRA-DISCOUNT TO WS-DISCOUNT-PCT
               END-IF

      *        IMPLICIT: Loyalty tier adds extra discount
               PERFORM CALCULATE-LOYALTY-TIER

               IF LOYAL-PLAT
                   ADD 3.00 TO WS-DISCOUNT-PCT
               ELSE IF LOYAL-GOLD
                   ADD 2.00 TO WS-DISCOUNT-PCT
               ELSE IF LOYAL-SILV
                   ADD 1.00 TO WS-DISCOUNT-PCT
               END-IF

      *        Cap total discount at 30%
               IF WS-DISCOUNT-PCT > 30.00
                   MOVE 30.00 TO WS-DISCOUNT-PCT
               END-IF

      *        Calculate new rate
               COMPUTE WS-NEW-RATE =
                   WS-MONTHLY-RATE * (1 - WS-DISCOUNT-PCT / 100)

      *        IMPLICIT: Loyalty credit = 2% of annual spend
               COMPUTE WS-LOYALTY-CREDIT =
                   WS-NEW-RATE * 12 * WS-LOYALTY-CREDIT-PCT / 100

               MOVE 'ACTIVE' TO WS-STATUS
               MOVE 'OK' TO WS-RESULT-CODE
           END-IF.

      *================================================================
      * BR-005: Determine loyalty tier from tenure
      *================================================================
       CALCULATE-LOYALTY-TIER.
           IF WS-ACCOUNT-TENURE-MO >= WS-LOYALTY-THRESHOLD-PLAT
               MOVE 'PLAT' TO WS-LOYALTY-TIER
           ELSE IF WS-ACCOUNT-TENURE-MO >= WS-LOYALTY-THRESHOLD-GOLD
               MOVE 'GOLD' TO WS-LOYALTY-TIER
           ELSE IF WS-ACCOUNT-TENURE-MO >= WS-LOYALTY-THRESHOLD-SILV
               MOVE 'SILV' TO WS-LOYALTY-TIER
           ELSE
               MOVE SPACES TO WS-LOYALTY-TIER
           END-IF.

      *================================================================
      * BR-006: Early termination fee calculation
      * BR-007: ETF cap
      *================================================================
       TERMINATE-CONTRACT.
      *    Only ACTIVE contracts can be terminated
           IF NOT CSTAT-ACTIVE
               MOVE 'R006' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

           IF STATUS-OK
      *        ETF = remaining months * per-month fee
               COMPUTE WS-ETF-AMOUNT =
                   WS-REMAINING-MONTHS * WS-ETF-PER-MONTH

      *        Cap at maximum ETF
               IF WS-ETF-AMOUNT > WS-ETF-MAX
                   MOVE WS-ETF-MAX TO WS-ETF-AMOUNT
               END-IF

      *        IMPLICIT: Loyalty platinum customers get 50% ETF reduction
               IF LOYAL-PLAT
                   COMPUTE WS-ETF-AMOUNT =
                       WS-ETF-AMOUNT * 0.50
               END-IF

               MOVE 'TERMINAT' TO WS-STATUS
               MOVE 'OK' TO WS-RESULT-CODE
           END-IF.

      *================================================================
      * BR-008: Modify contract (change auto-renew)
      *================================================================
       MODIFY-CONTRACT.
           IF NOT CSTAT-ACTIVE
               MOVE 'R007' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE
               MOVE 'OK' TO WS-RESULT-CODE
           END-IF.

      *================================================================
      * BR-009: Query contract
      *================================================================
       QUERY-CONTRACT.
           MOVE 'OK' TO WS-RESULT-CODE.
