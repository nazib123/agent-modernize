       IDENTIFICATION DIVISION.
       PROGRAM-ID. BILLING-DISPUTE-PROC.
       AUTHOR. LEGACY-TELECOM-SYSTEMS.
      *================================================================
      * BILLING DISPUTE RESOLUTION SYSTEM
      * Processes customer billing disputes for telecom services.
      * Validates dispute eligibility, calculates adjustments,
      * and routes to appropriate resolution workflow.
      *================================================================

       DATA DIVISION.
       WORKING-STORAGE SECTION.

       01  WS-DISPUTE-RECORD.
           05  WS-DISPUTE-ID           PIC X(12).
           05  WS-ACCOUNT-ID           PIC X(10).
           05  WS-CUSTOMER-TIER        PIC X(10).
               88  TIER-PLATINUM       VALUE 'PLATINUM'.
               88  TIER-GOLD           VALUE 'GOLD'.
               88  TIER-SILVER         VALUE 'SILVER'.
               88  TIER-BRONZE         VALUE 'BRONZE'.
           05  WS-DISPUTE-TYPE         PIC X(5).
               88  DTYPE-OVERCHG       VALUE 'OVCHG'.
               88  DTYPE-SVCFAIL       VALUE 'SVCFL'.
               88  DTYPE-LATFEE        VALUE 'LATFE'.
               88  DTYPE-TAXERR        VALUE 'TAXER'.
           05  WS-DISPUTE-AMOUNT       PIC 9(7)V99.
           05  WS-INVOICE-DATE         PIC 9(8).
           05  WS-DISPUTE-DATE         PIC 9(8).
           05  WS-INVOICE-TOTAL        PIC 9(7)V99.
           05  WS-ACCOUNT-BALANCE      PIC S9(7)V99.
           05  WS-MONTHS-AS-CUSTOMER   PIC 9(3).
           05  WS-PRIOR-DISPUTES-YTD   PIC 9(2).
           05  WS-SLA-VIOLATION-FLAG   PIC X(1).
               88  SLA-VIOLATED        VALUE 'Y'.
               88  SLA-NOT-VIOLATED    VALUE 'N'.

       01  WS-RESOLUTION-RECORD.
           05  WS-RESOLUTION-CODE      PIC X(4).
           05  WS-ADJUSTMENT-AMOUNT    PIC S9(7)V99.
           05  WS-ADJUSTMENT-TYPE      PIC X(10).
           05  WS-APPROVAL-LEVEL       PIC X(10).
           05  WS-CREDIT-APPLIED       PIC X(1).
           05  WS-ESCALATION-FLAG      PIC X(1).

       01  WS-ERROR-CODE              PIC X(4).
       01  WS-STATUS                  PIC X(2).
           88  STATUS-OK              VALUE 'OK'.
           88  STATUS-ERR             VALUE 'ER'.

       01  WS-MAX-AUTO-CREDIT         PIC 9(5)V99  VALUE 500.00.
       01  WS-MAX-DISPUTES-PER-YEAR   PIC 9(2)     VALUE 12.
       01  WS-DISPUTE-WINDOW-DAYS     PIC 9(3)     VALUE 90.
       01  WS-LOYALTY-THRESHOLD       PIC 9(3)     VALUE 24.
       01  WS-HIGH-VALUE-THRESHOLD    PIC 9(7)V99  VALUE 1000.00.

       PROCEDURE DIVISION.
       MAIN-PROCESS.
           PERFORM VALIDATE-DISPUTE-INPUT
           IF STATUS-OK
               PERFORM CHECK-DISPUTE-ELIGIBILITY
           END-IF
           IF STATUS-OK
               PERFORM CALCULATE-ADJUSTMENT
           END-IF
           IF STATUS-OK
               PERFORM DETERMINE-APPROVAL-LEVEL
           END-IF
           IF STATUS-OK
               PERFORM APPLY-RESOLUTION
           END-IF
           STOP RUN.

      *================================================================
      * BR-001: Validate dispute input fields
      *================================================================
       VALIDATE-DISPUTE-INPUT.
           IF WS-DISPUTE-ID = SPACES
               MOVE 'D001' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF WS-ACCOUNT-ID = SPACES
               MOVE 'D002' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF WS-DISPUTE-TYPE = SPACES
               MOVE 'D003' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF NOT (DTYPE-OVERCHG OR DTYPE-SVCFAIL
                        OR DTYPE-LATFEE OR DTYPE-TAXERR)
               MOVE 'D003' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF WS-DISPUTE-AMOUNT <= 0
               MOVE 'D004' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF WS-DISPUTE-AMOUNT > WS-INVOICE-TOTAL
               MOVE 'D005' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE
               SET STATUS-OK TO TRUE
           END-IF.

      *================================================================
      * BR-002: Check dispute eligibility (time window)
      * BR-003: Check dispute frequency limit
      *================================================================
       CHECK-DISPUTE-ELIGIBILITY.
      *    Dispute must be within 90 days of invoice
           COMPUTE WS-WORK-DAYS =
               FUNCTION INTEGER-OF-DATE(WS-DISPUTE-DATE) -
               FUNCTION INTEGER-OF-DATE(WS-INVOICE-DATE)
           IF WS-WORK-DAYS > WS-DISPUTE-WINDOW-DAYS
               MOVE 'D006' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

      *    Max disputes per year check
           IF WS-PRIOR-DISPUTES-YTD >= WS-MAX-DISPUTES-PER-YEAR
      *        IMPLICIT: Platinum customers exempt from frequency limit
               IF NOT TIER-PLATINUM
                   MOVE 'D007' TO WS-ERROR-CODE
                   SET STATUS-ERR TO TRUE
               END-IF
           END-IF.

      *================================================================
      * BR-004: Calculate adjustment amount based on dispute type
      * BR-005: SLA violation automatic full credit
      * BR-006: Loyalty bonus for long-term customers
      *================================================================
       CALCULATE-ADJUSTMENT.
           EVALUATE TRUE
      *        Service failure with SLA violation = full credit
               WHEN DTYPE-SVCFAIL AND SLA-VIOLATED
                   MOVE WS-DISPUTE-AMOUNT TO WS-ADJUSTMENT-AMOUNT
                   MOVE 'FULL-CREDIT' TO WS-ADJUSTMENT-TYPE

      *        Overcharge = full disputed amount
               WHEN DTYPE-OVERCHG
                   MOVE WS-DISPUTE-AMOUNT TO WS-ADJUSTMENT-AMOUNT
                   MOVE 'FULL-CREDIT' TO WS-ADJUSTMENT-TYPE

      *        Late fee dispute = 50% credit
               WHEN DTYPE-LATFEE
                   COMPUTE WS-ADJUSTMENT-AMOUNT =
                       WS-DISPUTE-AMOUNT * 0.50
                   MOVE 'PARTIAL-CRD' TO WS-ADJUSTMENT-TYPE

      *        Tax error = full credit + 10% goodwill
               WHEN DTYPE-TAXERR
                   COMPUTE WS-ADJUSTMENT-AMOUNT =
                       WS-DISPUTE-AMOUNT * 1.10
                   MOVE 'FULL+GDWILL' TO WS-ADJUSTMENT-TYPE

      *        Service failure without SLA = 75% credit
               WHEN DTYPE-SVCFAIL
                   COMPUTE WS-ADJUSTMENT-AMOUNT =
                       WS-DISPUTE-AMOUNT * 0.75
                   MOVE 'PARTIAL-CRD' TO WS-ADJUSTMENT-TYPE

               WHEN OTHER
                   MOVE 0 TO WS-ADJUSTMENT-AMOUNT
                   MOVE 'NO-ADJUST' TO WS-ADJUSTMENT-TYPE
           END-EVALUATE

      *    IMPLICIT: Loyalty bonus for customers > 24 months
           IF WS-MONTHS-AS-CUSTOMER > WS-LOYALTY-THRESHOLD
               IF WS-ADJUSTMENT-TYPE NOT = 'FULL-CREDIT'
                  AND WS-ADJUSTMENT-TYPE NOT = 'FULL+GDWILL'
                   COMPUTE WS-ADJUSTMENT-AMOUNT =
                       WS-ADJUSTMENT-AMOUNT * 1.15
               END-IF
           END-IF.

      *================================================================
      * BR-007: Determine approval level based on amount
      * BR-008: High-value dispute escalation
      *================================================================
       DETERMINE-APPROVAL-LEVEL.
           IF WS-ADJUSTMENT-AMOUNT <= WS-MAX-AUTO-CREDIT
               MOVE 'AUTO' TO WS-APPROVAL-LEVEL
           ELSE IF WS-ADJUSTMENT-AMOUNT <= WS-HIGH-VALUE-THRESHOLD
               MOVE 'SUPERVISOR' TO WS-APPROVAL-LEVEL
           ELSE
               MOVE 'MANAGER' TO WS-APPROVAL-LEVEL
               MOVE 'Y' TO WS-ESCALATION-FLAG
           END-IF

      *    IMPLICIT: Platinum always gets auto-approval up to $1000
           IF TIER-PLATINUM
               AND WS-ADJUSTMENT-AMOUNT <= WS-HIGH-VALUE-THRESHOLD
               MOVE 'AUTO' TO WS-APPROVAL-LEVEL
           END-IF.

      *================================================================
      * BR-009: Apply resolution to account
      * BR-010: Negative balance protection
      *================================================================
       APPLY-RESOLUTION.
      *    Apply credit if auto-approved
           IF WS-APPROVAL-LEVEL = 'AUTO'
               COMPUTE WS-ACCOUNT-BALANCE =
                   WS-ACCOUNT-BALANCE - WS-ADJUSTMENT-AMOUNT
               MOVE 'Y' TO WS-CREDIT-APPLIED

      *        IMPLICIT: Never let balance go below zero
               IF WS-ACCOUNT-BALANCE < 0
                   MOVE 0 TO WS-ACCOUNT-BALANCE
               END-IF
           ELSE
               MOVE 'N' TO WS-CREDIT-APPLIED
               MOVE 'PENDING' TO WS-RESOLUTION-CODE
           END-IF

      *    Set resolution code
           IF WS-CREDIT-APPLIED = 'Y'
               MOVE 'RSLV' TO WS-RESOLUTION-CODE
           END-IF.
