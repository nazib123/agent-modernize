       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCOUNT-MIGRATION-PROC.
       AUTHOR. LEGACY-TELECOM-SYSTEMS.
      *================================================================
      * ACCOUNT MIGRATION SYSTEM (MULTI-STEP)
      * Handles customer account migration between platforms:
      * eligibility check, service inventory validation, data
      * mapping, cutover scheduling, rollback handling, and
      * post-migration verification.
      *================================================================

       DATA DIVISION.
       WORKING-STORAGE SECTION.

       01  WS-MIGRATION-REQUEST.
           05  WS-ACCOUNT-ID           PIC X(10).
           05  WS-ACTION               PIC X(6).
               88  ACT-CHECK           VALUE 'CHECK'.
               88  ACT-PLAN            VALUE 'PLAN'.
               88  ACT-EXEC            VALUE 'EXEC'.
               88  ACT-VERIFY          VALUE 'VERIFY'.
               88  ACT-ROLLBK          VALUE 'ROLLBK'.
               88  ACT-QUERY           VALUE 'QUERY'.
           05  WS-SOURCE-PLATFORM      PIC X(6).
               88  PLAT-LEGACY         VALUE 'LEGACY'.
               88  PLAT-MIDTIER        VALUE 'MIDTIR'.
           05  WS-TARGET-PLATFORM      PIC X(6).
               88  PLAT-MODERN         VALUE 'MODERN'.
               88  PLAT-CLOUD          VALUE 'CLOUD'.
           05  WS-CUSTOMER-TYPE        PIC X(4).
               88  CTYPE-ENTE          VALUE 'ENTE'.
               88  CTYPE-SMB           VALUE 'SMB'.
               88  CTYPE-CONS          VALUE 'CONS'.
           05  WS-SERVICE-COUNT        PIC 9(3).
           05  WS-ACTIVE-ORDERS        PIC 9(3).
           05  WS-OPEN-TICKETS         PIC 9(3).
           05  WS-DATA-SIZE-GB         PIC 9(5).
           05  WS-CUTOVER-WINDOW-HR    PIC 9(2).

       01  WS-MIGRATION-RECORD.
           05  WS-MIG-STATUS           PIC X(10).
               88  MSTAT-ELIGIBLE      VALUE 'ELIGIBLE'.
               88  MSTAT-PLANNED       VALUE 'PLANNED'.
               88  MSTAT-EXECUTING     VALUE 'EXECUTING'.
               88  MSTAT-COMPLETE      VALUE 'COMPLETE'.
               88  MSTAT-ROLLEDBACK    VALUE 'ROLLEDBACK'.
               88  MSTAT-FAILED        VALUE 'FAILED'.
               88  MSTAT-VERIFIED      VALUE 'VERIFIED'.
           05  WS-COMPLEXITY           PIC X(6).
               88  CMPLX-LOW           VALUE 'LOW'.
               88  CMPLX-MED           VALUE 'MEDIUM'.
               88  CMPLX-HIGH          VALUE 'HIGH'.
           05  WS-EST-DURATION-HR      PIC 9(3).
           05  WS-SERVICES-MIGRATED    PIC 9(3).
           05  WS-SERVICES-FAILED      PIC 9(3).
           05  WS-ROLLBACK-AVAILABLE   PIC X(1).
               88  CAN-ROLLBACK        VALUE 'Y'.
               88  NO-ROLLBACK         VALUE 'N'.

       01  WS-RESULT-RECORD.
           05  WS-RESULT-CODE         PIC X(4).
           05  WS-RISK-SCORE          PIC 9(3).
           05  WS-ESTIMATED-COST      PIC 9(7)V99.

       01  WS-MAX-SERVICES-SIMPLE    PIC 9(3) VALUE 10.
       01  WS-MAX-SERVICES-MEDIUM    PIC 9(3) VALUE 50.
       01  WS-MAX-DATA-SIMPLE        PIC 9(5) VALUE 100.
       01  WS-MAX-DATA-MEDIUM        PIC 9(5) VALUE 1000.
       01  WS-COST-PER-SERVICE       PIC 9(5)V99 VALUE 150.00.
       01  WS-COST-PER-GB            PIC 9(3)V99 VALUE 2.50.
       01  WS-ENTE-MULTIPLIER        PIC 9(1)V99 VALUE 2.00.
       01  WS-SMB-MULTIPLIER         PIC 9(1)V99 VALUE 1.50.
       01  WS-CONS-MULTIPLIER        PIC 9(1)V99 VALUE 1.00.
       01  WS-MIN-CUTOVER-HR         PIC 9(2) VALUE 2.
       01  WS-MAX-OPEN-TICKETS       PIC 9(3) VALUE 5.
       01  WS-ROLLBACK-WINDOW-HR     PIC 9(2) VALUE 48.

       01  WS-ERROR-CODE              PIC X(4).
       01  WS-STATUS-FLAG             PIC X(2).
           88  STATUS-OK              VALUE 'OK'.
           88  STATUS-ERR             VALUE 'ER'.

       PROCEDURE DIVISION.
       MAIN-PROCESS.
           PERFORM VALIDATE-MIGRATION-REQUEST
           IF STATUS-OK
               EVALUATE TRUE
                   WHEN ACT-CHECK
                       PERFORM CHECK-ELIGIBILITY
                   WHEN ACT-PLAN
                       PERFORM PLAN-MIGRATION
                   WHEN ACT-EXEC
                       PERFORM EXECUTE-MIGRATION
                   WHEN ACT-VERIFY
                       PERFORM VERIFY-MIGRATION
                   WHEN ACT-ROLLBK
                       PERFORM ROLLBACK-MIGRATION
                   WHEN ACT-QUERY
                       PERFORM QUERY-MIGRATION
               END-EVALUATE
           END-IF
           STOP RUN.

      *================================================================
      * BR-001: Validate migration request
      *================================================================
       VALIDATE-MIGRATION-REQUEST.
           IF WS-ACCOUNT-ID = SPACES
               MOVE 'M001' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF WS-ACTION = SPACES
               MOVE 'M002' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF NOT (ACT-CHECK OR ACT-PLAN OR ACT-EXEC
                        OR ACT-VERIFY OR ACT-ROLLBK OR ACT-QUERY)
               MOVE 'M002' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF ACT-CHECK AND
                   (WS-SOURCE-PLATFORM = SPACES
                    OR WS-TARGET-PLATFORM = SPACES)
               MOVE 'M003' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF ACT-CHECK AND
                   WS-SOURCE-PLATFORM = WS-TARGET-PLATFORM
               MOVE 'M004' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE
               SET STATUS-OK TO TRUE
           END-IF.

      *================================================================
      * BR-002: Eligibility check
      * BR-003: Active orders block migration
      * BR-004: Open tickets limit
      *================================================================
       CHECK-ELIGIBILITY.
      *    No active orders allowed
           IF WS-ACTIVE-ORDERS > 0
               MOVE 'M005' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

      *    Max 5 open tickets
           IF STATUS-OK
               IF WS-OPEN-TICKETS > WS-MAX-OPEN-TICKETS
                   MOVE 'M006' TO WS-ERROR-CODE
                   SET STATUS-ERR TO TRUE
               END-IF
           END-IF

           IF STATUS-OK
      *        Determine complexity
               PERFORM ASSESS-COMPLEXITY

      *        Calculate risk score
               PERFORM CALCULATE-RISK-SCORE

               MOVE 'ELIGIBLE' TO WS-MIG-STATUS
               MOVE 'OK' TO WS-RESULT-CODE
           END-IF.

      *================================================================
      * BR-005: Complexity assessment
      *================================================================
       ASSESS-COMPLEXITY.
           IF WS-SERVICE-COUNT <= WS-MAX-SERVICES-SIMPLE
              AND WS-DATA-SIZE-GB <= WS-MAX-DATA-SIMPLE
               MOVE 'LOW' TO WS-COMPLEXITY
           ELSE IF WS-SERVICE-COUNT <= WS-MAX-SERVICES-MEDIUM
              AND WS-DATA-SIZE-GB <= WS-MAX-DATA-MEDIUM
               MOVE 'MEDIUM' TO WS-COMPLEXITY
           ELSE
               MOVE 'HIGH' TO WS-COMPLEXITY
           END-IF.

      *================================================================
      * BR-006: Risk score calculation
      * IMPLICIT: Weighted formula based on services, data, tickets
      *================================================================
       CALCULATE-RISK-SCORE.
           COMPUTE WS-RISK-SCORE =
               (WS-SERVICE-COUNT * 2)
               + (WS-DATA-SIZE-GB / 100)
               + (WS-OPEN-TICKETS * 10)

      *    IMPLICIT: Enterprise accounts get higher risk score
           IF CTYPE-ENTE
               COMPUTE WS-RISK-SCORE =
                   WS-RISK-SCORE * 1.5
           END-IF

      *    Cap at 100
           IF WS-RISK-SCORE > 100
               MOVE 100 TO WS-RISK-SCORE
           END-IF.

      *================================================================
      * BR-007: Plan migration
      * BR-008: Cost estimation
      *================================================================
       PLAN-MIGRATION.
           IF NOT MSTAT-ELIGIBLE
               MOVE 'M007' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

           IF STATUS-OK
      *        Estimate duration based on complexity
               EVALUATE TRUE
                   WHEN CMPLX-LOW
                       MOVE WS-MIN-CUTOVER-HR TO WS-EST-DURATION-HR
                   WHEN CMPLX-MED
                       COMPUTE WS-EST-DURATION-HR =
                           WS-MIN-CUTOVER-HR * 2
                   WHEN CMPLX-HIGH
                       COMPUTE WS-EST-DURATION-HR =
                           WS-MIN-CUTOVER-HR * 4
               END-EVALUATE

      *        Validate cutover window
               IF WS-CUTOVER-WINDOW-HR < WS-EST-DURATION-HR
                   MOVE 'M008' TO WS-ERROR-CODE
                   SET STATUS-ERR TO TRUE
               END-IF
           END-IF

           IF STATUS-OK
      *        Calculate cost
               COMPUTE WS-ESTIMATED-COST =
                   (WS-SERVICE-COUNT * WS-COST-PER-SERVICE)
                   + (WS-DATA-SIZE-GB * WS-COST-PER-GB)

      *        IMPLICIT: Customer type multiplier
               EVALUATE TRUE
                   WHEN CTYPE-ENTE
                       COMPUTE WS-ESTIMATED-COST =
                           WS-ESTIMATED-COST * WS-ENTE-MULTIPLIER
                   WHEN CTYPE-SMB
                       COMPUTE WS-ESTIMATED-COST =
                           WS-ESTIMATED-COST * WS-SMB-MULTIPLIER
                   WHEN CTYPE-CONS
                       COMPUTE WS-ESTIMATED-COST =
                           WS-ESTIMATED-COST * WS-CONS-MULTIPLIER
               END-EVALUATE

               MOVE 'PLANNED' TO WS-MIG-STATUS
               SET CAN-ROLLBACK TO TRUE
               MOVE 'OK' TO WS-RESULT-CODE
           END-IF.

      *================================================================
      * BR-009: Execute migration
      *================================================================
       EXECUTE-MIGRATION.
           IF NOT MSTAT-PLANNED
               MOVE 'M009' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

           IF STATUS-OK
               MOVE 'EXECUTING' TO WS-MIG-STATUS
               MOVE 'OK' TO WS-RESULT-CODE
           END-IF.

      *================================================================
      * BR-010: Verify migration
      * BR-011: Verification threshold
      *================================================================
       VERIFY-MIGRATION.
           IF NOT (MSTAT-EXECUTING OR MSTAT-COMPLETE)
               MOVE 'M010' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

           IF STATUS-OK
      *        Check all services migrated
               IF WS-SERVICES-FAILED > 0
      *            IMPLICIT: Partial migration auto-rolls back for Enterprise
                   IF CTYPE-ENTE
                       PERFORM ROLLBACK-MIGRATION
                   ELSE
                       MOVE 'COMPLETE' TO WS-MIG-STATUS
                       MOVE 'PARTIAL' TO WS-RESULT-CODE
                   END-IF
               ELSE
                   MOVE 'VERIFIED' TO WS-MIG-STATUS
                   SET NO-ROLLBACK TO TRUE
                   MOVE 'OK' TO WS-RESULT-CODE
               END-IF
           END-IF.

      *================================================================
      * BR-012: Rollback migration
      * BR-013: Rollback window
      *================================================================
       ROLLBACK-MIGRATION.
           IF NOT (MSTAT-EXECUTING OR MSTAT-COMPLETE)
               MOVE 'M011' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

      *    Check rollback is still available
           IF STATUS-OK AND NOT CAN-ROLLBACK
               MOVE 'M012' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

           IF STATUS-OK
               MOVE 'ROLLEDBACK' TO WS-MIG-STATUS
               SET NO-ROLLBACK TO TRUE
               MOVE 'OK' TO WS-RESULT-CODE
           END-IF.

      *================================================================
      * BR-014: Query migration status
      *================================================================
       QUERY-MIGRATION.
           MOVE 'OK' TO WS-RESULT-CODE.
