       IDENTIFICATION DIVISION.
       PROGRAM-ID. CIRCUIT-INVENTORY-PROC.
       AUTHOR. LEGACY-TELECOM-SYSTEMS.
      *================================================================
      * CIRCUIT INVENTORY MANAGEMENT SYSTEM
      * Manages telecom circuit lifecycle: assignment, modification,
      * decommission. Tracks circuit status, capacity allocation,
      * and cross-connect relationships.
      *================================================================

       DATA DIVISION.
       WORKING-STORAGE SECTION.

       01  WS-CIRCUIT-REQUEST.
           05  WS-CIRCUIT-ID           PIC X(15).
           05  WS-ACTION               PIC X(5).
               88  ACT-ASSIGN          VALUE 'ASGN'.
               88  ACT-MODIFY          VALUE 'MOD'.
               88  ACT-DECOM           VALUE 'DECOM'.
               88  ACT-QUERY           VALUE 'QUERY'.
           05  WS-CIRCUIT-TYPE         PIC X(5).
               88  CTYPE-DS1           VALUE 'DS1'.
               88  CTYPE-DS3           VALUE 'DS3'.
               88  CTYPE-OC3           VALUE 'OC3'.
               88  CTYPE-OC12          VALUE 'OC12'.
               88  CTYPE-ETH           VALUE 'ETH'.
           05  WS-SITE-A-CLLI         PIC X(11).
           05  WS-SITE-Z-CLLI         PIC X(11).
           05  WS-REQUESTED-BW        PIC 9(7).
           05  WS-CUSTOMER-ID         PIC X(10).
           05  WS-SERVICE-CLASS        PIC X(5).
               88  SCLASS-PREM         VALUE 'PREM'.
               88  SCLASS-STD          VALUE 'STD'.
               88  SCLASS-ECON         VALUE 'ECON'.

       01  WS-CIRCUIT-RECORD.
           05  WS-STATUS               PIC X(8).
               88  CSTAT-AVAILABLE     VALUE 'AVAIL'.
               88  CSTAT-ASSIGNED      VALUE 'ASSIGNED'.
               88  CSTAT-RESERVED      VALUE 'RESERVED'.
               88  CSTAT-DECOM         VALUE 'DECOM'.
           05  WS-ALLOCATED-BW        PIC 9(7).
           05  WS-MAX-BW              PIC 9(7).
           05  WS-CROSS-CONNECTS      PIC 9(3).
           05  WS-PARENT-CIRCUIT      PIC X(15).
           05  WS-CHILD-COUNT         PIC 9(3).
           05  WS-LAST-MODIFIED       PIC 9(8).
           05  WS-CREATED-DATE        PIC 9(8).

       01  WS-SITE-RECORD.
           05  WS-SITE-STATUS         PIC X(8).
               88  SITE-ACTIVE         VALUE 'ACTIVE'.
               88  SITE-INACTIVE       VALUE 'INACTIVE'.
           05  WS-SITE-CAPACITY       PIC 9(5).
           05  WS-SITE-USED           PIC 9(5).
           05  WS-SITE-TYPE           PIC X(5).
               88  SITE-COLO           VALUE 'COLO'.
               88  SITE-OWNED          VALUE 'OWNED'.

       01  WS-RESULT-RECORD.
           05  WS-RESULT-CODE         PIC X(4).
           05  WS-MONTHLY-COST        PIC 9(7)V99.
           05  WS-INSTALL-FEE         PIC 9(5)V99.
           05  WS-NEW-STATUS          PIC X(8).

       01  WS-ERROR-CODE              PIC X(4).
       01  WS-STATUS-FLAG             PIC X(2).
           88  STATUS-OK              VALUE 'OK'.
           88  STATUS-ERR             VALUE 'ER'.

       01  WS-DS1-BW                  PIC 9(7)  VALUE 1544.
       01  WS-DS3-BW                  PIC 9(7)  VALUE 44736.
       01  WS-OC3-BW                  PIC 9(7)  VALUE 155520.
       01  WS-OC12-BW                 PIC 9(7)  VALUE 622080.
       01  WS-ETH-MAX-BW             PIC 9(7)  VALUE 1000000.
       01  WS-MAX-CROSS-CONNECTS     PIC 9(3)  VALUE 64.
       01  WS-COLO-PREMIUM-PCT       PIC 9(2)  VALUE 15.

       PROCEDURE DIVISION.
       MAIN-PROCESS.
           PERFORM VALIDATE-CIRCUIT-REQUEST
           IF STATUS-OK
               EVALUATE TRUE
                   WHEN ACT-ASSIGN
                       PERFORM ASSIGN-CIRCUIT
                   WHEN ACT-MODIFY
                       PERFORM MODIFY-CIRCUIT
                   WHEN ACT-DECOM
                       PERFORM DECOMMISSION-CIRCUIT
                   WHEN ACT-QUERY
                       PERFORM QUERY-CIRCUIT
               END-EVALUATE
           END-IF
           STOP RUN.

      *================================================================
      * BR-001: Validate circuit request fields
      * BR-002: Validate circuit type bandwidth
      *================================================================
       VALIDATE-CIRCUIT-REQUEST.
           IF WS-CIRCUIT-ID = SPACES AND NOT ACT-ASSIGN
               MOVE 'C001' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF WS-ACTION = SPACES
               MOVE 'C002' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF NOT (ACT-ASSIGN OR ACT-MODIFY
                        OR ACT-DECOM OR ACT-QUERY)
               MOVE 'C002' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF ACT-ASSIGN AND WS-CUSTOMER-ID = SPACES
               MOVE 'C003' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF ACT-ASSIGN AND WS-CIRCUIT-TYPE = SPACES
               MOVE 'C004' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF ACT-ASSIGN
               AND (WS-SITE-A-CLLI = SPACES
                    OR WS-SITE-Z-CLLI = SPACES)
               MOVE 'C005' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE
               SET STATUS-OK TO TRUE
           END-IF

      *    Validate bandwidth for circuit type
           IF STATUS-OK AND ACT-ASSIGN
               EVALUATE TRUE
                   WHEN CTYPE-DS1
                       IF WS-REQUESTED-BW > WS-DS1-BW
                           MOVE 'C006' TO WS-ERROR-CODE
                           SET STATUS-ERR TO TRUE
                       END-IF
                   WHEN CTYPE-DS3
                       IF WS-REQUESTED-BW > WS-DS3-BW
                           MOVE 'C006' TO WS-ERROR-CODE
                           SET STATUS-ERR TO TRUE
                       END-IF
                   WHEN CTYPE-OC3
                       IF WS-REQUESTED-BW > WS-OC3-BW
                           MOVE 'C006' TO WS-ERROR-CODE
                           SET STATUS-ERR TO TRUE
                       END-IF
                   WHEN CTYPE-OC12
                       IF WS-REQUESTED-BW > WS-OC12-BW
                           MOVE 'C006' TO WS-ERROR-CODE
                           SET STATUS-ERR TO TRUE
                       END-IF
                   WHEN CTYPE-ETH
                       IF WS-REQUESTED-BW > WS-ETH-MAX-BW
                           MOVE 'C006' TO WS-ERROR-CODE
                           SET STATUS-ERR TO TRUE
                       END-IF
               END-EVALUATE
           END-IF.

      *================================================================
      * BR-003: Assign new circuit
      * BR-004: Site validation and capacity check
      * BR-005: Cross-connect limit enforcement
      *================================================================
       ASSIGN-CIRCUIT.
      *    Check both sites are active
           IF NOT SITE-ACTIVE
               MOVE 'C007' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

      *    Check site capacity
           IF STATUS-OK
               IF WS-SITE-USED >= WS-SITE-CAPACITY
                   MOVE 'C008' TO WS-ERROR-CODE
                   SET STATUS-ERR TO TRUE
               END-IF
           END-IF

      *    Check cross-connect limit
           IF STATUS-OK
               IF WS-CROSS-CONNECTS >= WS-MAX-CROSS-CONNECTS
      *            IMPLICIT: Premium service class can exceed by 50%
                   IF NOT SCLASS-PREM
                       MOVE 'C009' TO WS-ERROR-CODE
                       SET STATUS-ERR TO TRUE
                   ELSE
                       IF WS-CROSS-CONNECTS >=
                           (WS-MAX-CROSS-CONNECTS * 1.5)
                           MOVE 'C009' TO WS-ERROR-CODE
                           SET STATUS-ERR TO TRUE
                       END-IF
                   END-IF
               END-IF
           END-IF

      *    Assign the circuit
           IF STATUS-OK
               MOVE 'ASSIGNED' TO WS-NEW-STATUS
               MOVE WS-REQUESTED-BW TO WS-ALLOCATED-BW
               ADD 1 TO WS-CROSS-CONNECTS
               ADD 1 TO WS-SITE-USED
               PERFORM CALCULATE-CIRCUIT-COST
           END-IF.

      *================================================================
      * BR-006: Modify circuit bandwidth
      * BR-007: Downgrade restrictions
      *================================================================
       MODIFY-CIRCUIT.
      *    Circuit must be in ASSIGNED status
           IF NOT CSTAT-ASSIGNED
               MOVE 'C010' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

      *    New bandwidth must not exceed circuit type max
           IF STATUS-OK
               IF WS-REQUESTED-BW > WS-MAX-BW
                   MOVE 'C011' TO WS-ERROR-CODE
                   SET STATUS-ERR TO TRUE
               END-IF
           END-IF

      *    IMPLICIT: Cannot downgrade premium circuits below 50%
           IF STATUS-OK AND SCLASS-PREM
               IF WS-REQUESTED-BW < (WS-ALLOCATED-BW * 0.50)
                   MOVE 'C012' TO WS-ERROR-CODE
                   SET STATUS-ERR TO TRUE
               END-IF
           END-IF

           IF STATUS-OK
               MOVE WS-REQUESTED-BW TO WS-ALLOCATED-BW
               PERFORM CALCULATE-CIRCUIT-COST
           END-IF.

      *================================================================
      * BR-008: Decommission circuit
      * BR-009: Parent-child dependency check
      *================================================================
       DECOMMISSION-CIRCUIT.
      *    Circuit must be ASSIGNED or RESERVED
           IF NOT (CSTAT-ASSIGNED OR CSTAT-RESERVED)
               MOVE 'C013' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

      *    Cannot decommission parent with active children
           IF STATUS-OK AND WS-CHILD-COUNT > 0
               MOVE 'C014' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

           IF STATUS-OK
               MOVE 'DECOM' TO WS-NEW-STATUS
               MOVE 0 TO WS-ALLOCATED-BW
               SUBTRACT 1 FROM WS-CROSS-CONNECTS
               SUBTRACT 1 FROM WS-SITE-USED
               MOVE 0 TO WS-MONTHLY-COST
           END-IF.

      *================================================================
      * BR-010: Query circuit details
      *================================================================
       QUERY-CIRCUIT.
           MOVE 'OK' TO WS-RESULT-CODE.

      *================================================================
      * BR-011: Calculate monthly cost
      * BR-012: Colocation premium
      *================================================================
       CALCULATE-CIRCUIT-COST.
      *    Base cost per Kbps depends on circuit type
           EVALUATE TRUE
               WHEN CTYPE-DS1
                   COMPUTE WS-MONTHLY-COST =
                       WS-ALLOCATED-BW * 0.15
               WHEN CTYPE-DS3
                   COMPUTE WS-MONTHLY-COST =
                       WS-ALLOCATED-BW * 0.08
               WHEN CTYPE-OC3
                   COMPUTE WS-MONTHLY-COST =
                       WS-ALLOCATED-BW * 0.04
               WHEN CTYPE-OC12
                   COMPUTE WS-MONTHLY-COST =
                       WS-ALLOCATED-BW * 0.02
               WHEN CTYPE-ETH
                   COMPUTE WS-MONTHLY-COST =
                       WS-ALLOCATED-BW * 0.01
           END-EVALUATE

      *    Service class multiplier
           EVALUATE TRUE
               WHEN SCLASS-PREM
                   COMPUTE WS-MONTHLY-COST =
                       WS-MONTHLY-COST * 1.50
               WHEN SCLASS-STD
                   COMPUTE WS-MONTHLY-COST =
                       WS-MONTHLY-COST * 1.00
               WHEN SCLASS-ECON
                   COMPUTE WS-MONTHLY-COST =
                       WS-MONTHLY-COST * 0.75
           END-EVALUATE

      *    IMPLICIT: Colocation site adds 15% premium
           IF SITE-COLO
               COMPUTE WS-MONTHLY-COST =
                   WS-MONTHLY-COST * (1 + WS-COLO-PREMIUM-PCT / 100)
           END-IF

      *    Install fee = first month cost
           MOVE WS-MONTHLY-COST TO WS-INSTALL-FEE.
