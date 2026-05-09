       IDENTIFICATION DIVISION.
       PROGRAM-ID. SERVICE-ACTIVATION-PROC.
       AUTHOR. LEGACY-TELECOM-SYSTEMS.
      *================================================================
      * SERVICE ACTIVATION AND PROVISIONING SYSTEM
      * Handles activation of new telecom services including
      * port validation, capacity checks, feature bundling,
      * and provisioning workflow scheduling.
      *================================================================

       DATA DIVISION.
       WORKING-STORAGE SECTION.

       01  WS-SERVICE-REQUEST.
           05  WS-REQUEST-ID           PIC X(12).
           05  WS-ACCOUNT-ID           PIC X(10).
           05  WS-SERVICE-TYPE         PIC X(5).
               88  STYPE-VOICE         VALUE 'VOICE'.
               88  STYPE-DATA          VALUE 'DATA'.
               88  STYPE-VIDEO         VALUE 'VIDEO'.
               88  STYPE-BUNDLE        VALUE 'BNDL'.
           05  WS-BANDWIDTH-MBPS       PIC 9(5).
           05  WS-PORT-TYPE            PIC X(4).
               88  PORT-COPPER         VALUE 'CU'.
               88  PORT-FIBER          VALUE 'FBR'.
               88  PORT-WIRELESS       VALUE 'WLS'.
           05  WS-ADDRESS-CLLI         PIC X(11).
           05  WS-REQUESTED-DATE       PIC 9(8).
           05  WS-CURRENT-DATE         PIC 9(8).
           05  WS-CUSTOMER-TIER        PIC X(10).
               88  TIER-ENTERPRISE     VALUE 'ENTERPRISE'.
               88  TIER-BUSINESS       VALUE 'BUSINESS'.
               88  TIER-RESIDENTIAL    VALUE 'RESIDENTIA'.

       01  WS-FACILITY-RECORD.
           05  WS-AVAILABLE-PORTS      PIC 9(4).
           05  WS-TOTAL-CAPACITY-MBPS  PIC 9(7).
           05  WS-USED-CAPACITY-MBPS   PIC 9(7).
           05  WS-MAINTENANCE-FLAG     PIC X(1).
               88  FACILITY-IN-MAINT   VALUE 'Y'.
               88  FACILITY-ACTIVE     VALUE 'N'.

       01  WS-PROVISIONING-RECORD.
           05  WS-PROVISION-TYPE       PIC X(10).
           05  WS-INSTALL-DATE         PIC 9(8).
           05  WS-SLA-TIER             PIC X(10).
           05  WS-ESTIMATED-HOURS      PIC 9(3).
           05  WS-TECH-REQUIRED        PIC X(1).
           05  WS-FEATURES-INCLUDED    PIC X(50).
           05  WS-MONTHLY-RATE         PIC 9(5)V99.
           05  WS-ACTIVATION-FEE       PIC 9(5)V99.

       01  WS-ERROR-CODE              PIC X(4).
       01  WS-STATUS                  PIC X(2).
           88  STATUS-OK              VALUE 'OK'.
           88  STATUS-ERR             VALUE 'ER'.

       01  WS-MIN-LEAD-DAYS          PIC 9(2) VALUE 3.
       01  WS-MAX-BANDWIDTH-COPPER   PIC 9(5) VALUE 100.
       01  WS-MAX-BANDWIDTH-FIBER    PIC 9(5) VALUE 10000.
       01  WS-MAX-BANDWIDTH-WLS      PIC 9(5) VALUE 1000.
       01  WS-CAPACITY-THRESHOLD     PIC 9(2) VALUE 85.

       PROCEDURE DIVISION.
       MAIN-PROCESS.
           PERFORM VALIDATE-SERVICE-REQUEST
           IF STATUS-OK
               PERFORM CHECK-FACILITY-AVAILABILITY
           END-IF
           IF STATUS-OK
               PERFORM DETERMINE-PROVISIONING-PLAN
           END-IF
           IF STATUS-OK
               PERFORM CALCULATE-PRICING
           END-IF
           IF STATUS-OK
               PERFORM SCHEDULE-ACTIVATION
           END-IF
           STOP RUN.

      *================================================================
      * BR-001: Validate service request fields
      * BR-002: Bandwidth must match port type limits
      *================================================================
       VALIDATE-SERVICE-REQUEST.
           IF WS-REQUEST-ID = SPACES
               MOVE 'S001' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF WS-ACCOUNT-ID = SPACES
               MOVE 'S002' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF WS-SERVICE-TYPE = SPACES
               MOVE 'S003' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE IF NOT (STYPE-VOICE OR STYPE-DATA
                        OR STYPE-VIDEO OR STYPE-BUNDLE)
               MOVE 'S003' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           ELSE
               SET STATUS-OK TO TRUE
           END-IF

      *    Bandwidth validation by port type
           IF STATUS-OK
               EVALUATE TRUE
                   WHEN PORT-COPPER
                       IF WS-BANDWIDTH-MBPS > WS-MAX-BANDWIDTH-COPPER
                           MOVE 'S004' TO WS-ERROR-CODE
                           SET STATUS-ERR TO TRUE
                       END-IF
                   WHEN PORT-FIBER
                       IF WS-BANDWIDTH-MBPS > WS-MAX-BANDWIDTH-FIBER
                           MOVE 'S004' TO WS-ERROR-CODE
                           SET STATUS-ERR TO TRUE
                       END-IF
                   WHEN PORT-WIRELESS
                       IF WS-BANDWIDTH-MBPS > WS-MAX-BANDWIDTH-WLS
                           MOVE 'S004' TO WS-ERROR-CODE
                           SET STATUS-ERR TO TRUE
                       END-IF
               END-EVALUATE
           END-IF

      *    IMPLICIT: Video service requires minimum 25 Mbps
           IF STATUS-OK AND STYPE-VIDEO
               IF WS-BANDWIDTH-MBPS < 25
                   MOVE 'S005' TO WS-ERROR-CODE
                   SET STATUS-ERR TO TRUE
               END-IF
           END-IF

      *    IMPLICIT: Bundle requires fiber or wireless
           IF STATUS-OK AND STYPE-BUNDLE
               IF PORT-COPPER
                   MOVE 'S006' TO WS-ERROR-CODE
                   SET STATUS-ERR TO TRUE
               END-IF
           END-IF.

      *================================================================
      * BR-003: Check facility port availability
      * BR-004: Check capacity threshold
      * BR-005: Facility maintenance block
      *================================================================
       CHECK-FACILITY-AVAILABILITY.
      *    Facility must not be in maintenance
           IF FACILITY-IN-MAINT
               MOVE 'S007' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

      *    Must have available ports
           IF STATUS-OK AND WS-AVAILABLE-PORTS <= 0
               MOVE 'S008' TO WS-ERROR-CODE
               SET STATUS-ERR TO TRUE
           END-IF

      *    Check capacity utilization threshold
           IF STATUS-OK
               COMPUTE WS-WORK-PCT =
                   ((WS-USED-CAPACITY-MBPS + WS-BANDWIDTH-MBPS)
                    * 100) / WS-TOTAL-CAPACITY-MBPS
               IF WS-WORK-PCT > WS-CAPACITY-THRESHOLD
      *            IMPLICIT: Enterprise tier exempt from capacity limit
                   IF NOT TIER-ENTERPRISE
                       MOVE 'S009' TO WS-ERROR-CODE
                       SET STATUS-ERR TO TRUE
                   END-IF
               END-IF
           END-IF.

      *================================================================
      * BR-006: Determine provisioning type and SLA
      * BR-007: Feature bundling logic
      *================================================================
       DETERMINE-PROVISIONING-PLAN.
      *    Set provisioning type based on port
           EVALUATE TRUE
               WHEN PORT-FIBER
                   MOVE 'FIBER-INST' TO WS-PROVISION-TYPE
                   MOVE 8 TO WS-ESTIMATED-HOURS
                   MOVE 'Y' TO WS-TECH-REQUIRED
               WHEN PORT-COPPER
                   MOVE 'COPPER-ACT' TO WS-PROVISION-TYPE
                   MOVE 4 TO WS-ESTIMATED-HOURS
                   MOVE 'Y' TO WS-TECH-REQUIRED
               WHEN PORT-WIRELESS
                   MOVE 'WLS-PROV' TO WS-PROVISION-TYPE
                   MOVE 2 TO WS-ESTIMATED-HOURS
                   MOVE 'N' TO WS-TECH-REQUIRED
           END-EVALUATE

      *    Set SLA tier based on customer tier
           EVALUATE TRUE
               WHEN TIER-ENTERPRISE
                   MOVE 'PREMIUM' TO WS-SLA-TIER
               WHEN TIER-BUSINESS
                   MOVE 'STANDARD' TO WS-SLA-TIER
               WHEN TIER-RESIDENTIAL
                   MOVE 'BASIC' TO WS-SLA-TIER
           END-EVALUATE

      *    Feature bundling
           EVALUATE TRUE
               WHEN STYPE-BUNDLE
                   MOVE 'VOICE+DATA+VIDEO' TO WS-FEATURES-INCLUDED
               WHEN STYPE-VOICE
                   MOVE 'VOICE-ONLY' TO WS-FEATURES-INCLUDED
               WHEN STYPE-DATA
                   MOVE 'DATA-ONLY' TO WS-FEATURES-INCLUDED
               WHEN STYPE-VIDEO
                   MOVE 'VIDEO+DATA' TO WS-FEATURES-INCLUDED
           END-EVALUATE.

      *================================================================
      * BR-008: Calculate monthly rate and activation fee
      * BR-009: Enterprise discount on activation fee
      *================================================================
       CALCULATE-PRICING.
      *    Base rate per Mbps depends on port type
           EVALUATE TRUE
               WHEN PORT-FIBER
                   COMPUTE WS-MONTHLY-RATE =
                       WS-BANDWIDTH-MBPS * 0.50
               WHEN PORT-COPPER
                   COMPUTE WS-MONTHLY-RATE =
                       WS-BANDWIDTH-MBPS * 1.20
               WHEN PORT-WIRELESS
                   COMPUTE WS-MONTHLY-RATE =
                       WS-BANDWIDTH-MBPS * 0.80
           END-EVALUATE

      *    Bundle discount: 20% off monthly rate
           IF STYPE-BUNDLE
               COMPUTE WS-MONTHLY-RATE =
                   WS-MONTHLY-RATE * 0.80
           END-IF

      *    Activation fee based on tech requirement
           IF WS-TECH-REQUIRED = 'Y'
               MOVE 99.99 TO WS-ACTIVATION-FEE
           ELSE
               MOVE 0 TO WS-ACTIVATION-FEE
           END-IF

      *    IMPLICIT: Enterprise gets 50% off activation fee
           IF TIER-ENTERPRISE
               COMPUTE WS-ACTIVATION-FEE =
                   WS-ACTIVATION-FEE * 0.50
           END-IF.

      *================================================================
      * BR-010: Schedule activation date
      * BR-011: Enterprise priority scheduling
      *================================================================
       SCHEDULE-ACTIVATION.
      *    Must be at least 3 days lead time
           COMPUTE WS-WORK-DAYS =
               FUNCTION INTEGER-OF-DATE(WS-REQUESTED-DATE) -
               FUNCTION INTEGER-OF-DATE(WS-CURRENT-DATE)
           IF WS-WORK-DAYS < WS-MIN-LEAD-DAYS
               COMPUTE WS-INSTALL-DATE =
                   WS-CURRENT-DATE + WS-MIN-LEAD-DAYS
           ELSE
               MOVE WS-REQUESTED-DATE TO WS-INSTALL-DATE
           END-IF

      *    IMPLICIT: Enterprise gets next-day activation for wireless
           IF TIER-ENTERPRISE AND PORT-WIRELESS
               COMPUTE WS-INSTALL-DATE =
                   WS-CURRENT-DATE + 1
               MOVE 1 TO WS-ESTIMATED-HOURS
           END-IF.
