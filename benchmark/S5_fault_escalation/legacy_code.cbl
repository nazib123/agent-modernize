       IDENTIFICATION DIVISION.
       PROGRAM-ID. FAULT-TICKET-ESCALATION.
       AUTHOR. LEGACY-TELECOM-SYSTEMS.
      *================================================================
      * FAULT TICKET ESCALATION SYSTEM
      * Manages trouble ticket lifecycle: creation, severity assessment,
      * SLA tracking, escalation, and resolution. Implements tiered
      * escalation based on severity, elapsed time, and customer tier.
      *================================================================

       DATA DIVISION.
       WORKING-STORAGE SECTION.

       01  WS-TICKET-REQUEST.
           05  WS-TICKET-ID            PIC X(12).
           05  WS-ACTION               PIC X(6).
               88  ACT-CREATE          VALUE 'CREATE'.
               88  ACT-UPDATE          VALUE 'UPDATE'.
               88  ACT-ESCAL           VALUE 'ESCAL'.
               88  ACT-RESOLVE         VALUE 'RESOLV'.
               88  ACT-QUERY           VALUE 'QUERY'.
           05  WS-FAULT-TYPE           PIC X(6).
               88  FTYPE-OUTAGE        VALUE 'OUTAGE'.
               88  FTYPE-DEGRAD        VALUE 'DEGRAD'.
               88  FTYPE-INTERM        VALUE 'INTERM'.
               88  FTYPE-CONFIG        VALUE 'CONFIG'.
           05  WS-SEVERITY             PIC 9(1).
               88  SEV-CRITICAL        VALUE 1.
               88  SEV-MAJOR           VALUE 2.
               88  SEV-MINOR           VALUE 3.
               88  SEV-INFO            VALUE 4.
           05  WS-CUSTOMER-TIER        PIC X(4).
               88  TIER-PLAT           VALUE 'PLAT'.
               88  TIER-GOLD           VALUE 'GOLD'.
               88  TIER-SILV           VALUE 'SILV'.
               88  TIER-BRNZ           VALUE 'BRNZ'.
           05  WS-AFFECTED-CIRCUITS    PIC 9(5).
           05  WS-DESCRIPTION          PIC X(200).
           05  WS-RESOLUTION-CODE      PIC X(6).

       01  WS-TICKET-RECORD.
           05  WS-STATUS               PIC X(8).
               88  TSTAT-OPEN          VALUE 'OPEN'.
               88  TSTAT-WORKING       VALUE 'WORKING'.
               88  TSTAT-ESCALD        VALUE 'ESCALATD'.
               88  TSTAT-RESOLVED      VALUE 'RESOLVED'.
               88  TSTAT-CLOSED        VALUE 'CLOSED'.
           05  WS-CURRENT-LEVEL        PIC 9(1).
           05  WS-MAX-LEVEL            PIC 9(1) VALUE 4.
           05  WS-CREATED-TIME         PIC 9(14).
           05  WS-ELAPSED-MINUTES      PIC 9(6).
           05  WS-SLA-MINUTES          PIC 9(6).
           05  WS-SLA-BREACHED         PIC X(1).
               88  SLA-OK              VALUE 'N'.
               88  SLA-BREACHED        VALUE 'Y'.
           05  WS-ESCALATION-COUNT     PIC 9(2).

       01  WS-SLA-CRITICAL            PIC 9(6) VALUE 60.
       01  WS-SLA-MAJOR               PIC 9(6) VALUE 240.
       01  WS-SLA-MINOR               PIC 9(6) VALUE 1440.
       01  WS-SLA-INFO                PIC 9(6) VALUE 4320.

       01  WS-PLAT-SLA-REDUCTION     PIC 9(2) VALUE 50.
       01  WS-GOLD-SLA-REDUCTION     PIC 9(2) VALUE 25.

       01  WS-AUTO-ESCAL-THRESHOLD   PIC 9(3) VALUE 100.
       01  WS-MAX-ESCALATIONS        PIC 9(2) VALUE 5.

       01  WS-RESULT-CODE             PIC X(4).
       01  WS-STATUS-FLAG             PIC X(2).
           88  STATUS-OK              VALUE 'OK'.
           88  STATUS-ERR             VALUE 'ER'.

       PROCEDURE DIVISION.
       MAIN-PROCESS.
           PERFORM VALIDATE-TICKET-REQUEST
           IF STATUS-OK
               EVALUATE TRUE
                   WHEN ACT-CREATE
                       PERFORM CREATE-TICKET
                   WHEN ACT-UPDATE
                       PERFORM UPDATE-TICKET
                   WHEN ACT-ESCAL
                       PERFORM ESCALATE-TICKET
                   WHEN ACT-RESOLVE
                       PERFORM RESOLVE-TICKET
                   WHEN ACT-QUERY
                       PERFORM QUERY-TICKET
               END-EVALUATE
           END-IF
           STOP RUN.

      *================================================================
      * BR-001: Validate ticket request
      *================================================================
       VALIDATE-TICKET-REQUEST.
           IF WS-ACTION = SPACES
               MOVE 'T001' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF NOT (ACT-CREATE OR ACT-UPDATE
                        OR ACT-ESCAL OR ACT-RESOLVE OR ACT-QUERY)
               MOVE 'T001' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF ACT-CREATE AND WS-FAULT-TYPE = SPACES
               MOVE 'T002' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF ACT-CREATE AND
                   (WS-SEVERITY < 1 OR WS-SEVERITY > 4)
               MOVE 'T003' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF (ACT-UPDATE OR ACT-ESCAL OR ACT-RESOLVE)
                   AND WS-TICKET-ID = SPACES
               MOVE 'T004' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE
               SET STATUS-OK TO TRUE
           END-IF.

      *================================================================
      * BR-002: Create ticket with severity-based SLA
      * BR-003: Customer tier SLA adjustment
      *================================================================
       CREATE-TICKET.
           MOVE 'OPEN' TO WS-STATUS
           MOVE 1 TO WS-CURRENT-LEVEL
           MOVE 0 TO WS-ESCALATION-COUNT

      *    Set SLA based on severity
           EVALUATE TRUE
               WHEN SEV-CRITICAL
                   MOVE WS-SLA-CRITICAL TO WS-SLA-MINUTES
               WHEN SEV-MAJOR
                   MOVE WS-SLA-MAJOR TO WS-SLA-MINUTES
               WHEN SEV-MINOR
                   MOVE WS-SLA-MINOR TO WS-SLA-MINUTES
               WHEN SEV-INFO
                   MOVE WS-SLA-INFO TO WS-SLA-MINUTES
           END-EVALUATE

      *    IMPLICIT: Customer tier reduces SLA target
           IF TIER-PLAT
               COMPUTE WS-SLA-MINUTES =
                   WS-SLA-MINUTES * (100 - WS-PLAT-SLA-REDUCTION) / 100
           ELSE IF TIER-GOLD
               COMPUTE WS-SLA-MINUTES =
                   WS-SLA-MINUTES * (100 - WS-GOLD-SLA-REDUCTION) / 100
           END-IF

      *    IMPLICIT: Outage with >100 circuits auto-escalates to Sev 1
           IF FTYPE-OUTAGE AND
              WS-AFFECTED-CIRCUITS > WS-AUTO-ESCAL-THRESHOLD
               MOVE 1 TO WS-SEVERITY
               MOVE WS-SLA-CRITICAL TO WS-SLA-MINUTES
               MOVE 2 TO WS-CURRENT-LEVEL
           END-IF

           SET SLA-OK TO TRUE
           MOVE 'OK' TO WS-RESULT-CODE.

      *================================================================
      * BR-004: Update ticket status
      *================================================================
       UPDATE-TICKET.
           IF TSTAT-RESOLVED OR TSTAT-CLOSED
               MOVE 'T005' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE
               MOVE 'WORKING' TO WS-STATUS
               MOVE 'OK' TO WS-RESULT-CODE
           END-IF.

      *================================================================
      * BR-005: Escalate ticket
      * BR-006: Escalation level limits
      * BR-007: SLA breach check on escalation
      *================================================================
       ESCALATE-TICKET.
      *    Cannot escalate resolved/closed tickets
           IF TSTAT-RESOLVED OR TSTAT-CLOSED
               MOVE 'T006' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

      *    Check escalation limit
           IF STATUS-OK
               IF WS-ESCALATION-COUNT >= WS-MAX-ESCALATIONS
                   MOVE 'T007' TO WS-ERROR-CODE
                   SET STATUS-ERR TO TRUE
               END-IF
           END-IF

      *    Check if already at max level
           IF STATUS-OK
               IF WS-CURRENT-LEVEL >= WS-MAX-LEVEL
                   MOVE 'T008' TO WS-ERROR-CODE
                   SET STATUS-ERR TO TRUE
               END-IF
           END-IF

           IF STATUS-OK
               ADD 1 TO WS-CURRENT-LEVEL
               ADD 1 TO WS-ESCALATION-COUNT
               MOVE 'ESCALATD' TO WS-STATUS

      *        Check SLA breach
               IF WS-ELAPSED-MINUTES > WS-SLA-MINUTES
                   SET SLA-BREACHED TO TRUE
               END-IF

      *        IMPLICIT: Critical severity auto-notifies VP level
               IF SEV-CRITICAL AND WS-CURRENT-LEVEL >= 3
                   MOVE 'VP-NOTIFY' TO WS-RESULT-CODE
               ELSE
                   MOVE 'OK' TO WS-RESULT-CODE
               END-IF
           END-IF.

      *================================================================
      * BR-008: Resolve ticket
      * BR-009: Resolution requires code
      *================================================================
       RESOLVE-TICKET.
           IF TSTAT-CLOSED
               MOVE 'T009' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF WS-RESOLUTION-CODE = SPACES
               MOVE 'T010' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE
               MOVE 'RESOLVED' TO WS-STATUS

      *        IMPLICIT: SLA breach flag set if resolved after SLA
               IF WS-ELAPSED-MINUTES > WS-SLA-MINUTES
                   SET SLA-BREACHED TO TRUE
               END-IF

               MOVE 'OK' TO WS-RESULT-CODE
           END-IF.

      *================================================================
      * BR-010: Query ticket
      *================================================================
       QUERY-TICKET.
           IF WS-TICKET-ID = SPACES
               MOVE 'T004' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE
               MOVE 'OK' TO WS-RESULT-CODE
           END-IF.
