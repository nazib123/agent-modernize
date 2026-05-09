       IDENTIFICATION DIVISION.
       PROGRAM-ID. ORDER-VALIDATION-PROC.
       AUTHOR. TELECOM-LEGACY-SYSTEMS.
       DATE-WRITTEN. 1998-03-15.
      *================================================================
      * ORDER VALIDATION AND PROCESSING SYSTEM
      * Validates and processes wireline service orders for enterprise
      * customers. Handles new connects, disconnects, and modifications.
      * Called by: MAIN-ORDER-ENTRY (CICS transaction ORDR)
      * Last modified: 2005-11-20 (added suspend check - ticket #4472)
      *================================================================

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ORDER-FILE ASSIGN TO 'ORDFILE'
               ORGANIZATION IS INDEXED
               ACCESS MODE IS DYNAMIC
               RECORD KEY IS ORD-ORDER-ID.
           SELECT ACCOUNT-FILE ASSIGN TO 'ACCTFILE'
               ORGANIZATION IS INDEXED
               ACCESS MODE IS RANDOM
               RECORD KEY IS ACCT-ACCOUNT-ID.
           SELECT INVENTORY-FILE ASSIGN TO 'INVFILE'
               ORGANIZATION IS INDEXED
               ACCESS MODE IS RANDOM
               RECORD KEY IS INV-PRODUCT-ID.

       DATA DIVISION.
       WORKING-STORAGE SECTION.

       01  WS-ORDER-RECORD.
           05  WS-ORDER-ID          PIC X(12).
           05  WS-ACCOUNT-ID        PIC X(10).
           05  WS-ORDER-TYPE        PIC X(3).
               88  VALID-ORDER-TYPE VALUE 'NEW' 'DIS' 'MOD'.
           05  WS-PRODUCT-ID        PIC X(8).
           05  WS-QUANTITY           PIC 9(3).
           05  WS-UNIT-PRICE        PIC 9(7)V99.
           05  WS-DISCOUNT-PCT      PIC 9(2)V99.
           05  WS-TAX-RATE          PIC 9(1)V9999.
           05  WS-ORDER-DATE        PIC X(10).
           05  WS-REQUESTED-DUE     PIC X(10).
           05  WS-PRIORITY          PIC X(1).
               88  VALID-PRIORITY   VALUE 'S' 'H' 'N'.
           05  WS-NOTES             PIC X(200).

       01  WS-ACCOUNT-RECORD.
           05  ACCT-ACCOUNT-ID      PIC X(10).
           05  ACCT-STATUS          PIC X(3).
               88  ACCT-ACTIVE      VALUE 'ACT'.
               88  ACCT-SUSPENDED   VALUE 'SUS'.
               88  ACCT-CLOSED      VALUE 'CLO'.
               88  ACCT-PENDING     VALUE 'PND'.
           05  ACCT-CREDIT-LIMIT    PIC 9(9)V99.
           05  ACCT-CURRENT-BAL     PIC S9(9)V99.
           05  ACCT-ENTERPRISE-NAME PIC X(50).
           05  ACCT-REGION          PIC X(4).
           05  ACCT-TIER            PIC X(1).
               88  TIER-PLATINUM    VALUE 'P'.
               88  TIER-GOLD        VALUE 'G'.
               88  TIER-SILVER      VALUE 'S'.
               88  TIER-STANDARD    VALUE 'T'.
           05  ACCT-PAST-DUE-AMT   PIC 9(7)V99.
           05  ACCT-LAST-PAY-DATE  PIC X(10).

       01  WS-INVENTORY-RECORD.
           05  INV-PRODUCT-ID       PIC X(8).
           05  INV-PRODUCT-NAME     PIC X(40).
           05  INV-AVAILABLE-QTY    PIC 9(5).
           05  INV-RESERVED-QTY     PIC 9(5).
           05  INV-MIN-ORDER-QTY    PIC 9(3).
           05  INV-MAX-ORDER-QTY    PIC 9(3).
           05  INV-STATUS           PIC X(1).
               88  INV-AVAILABLE    VALUE 'A'.
               88  INV-DISCONTINUED VALUE 'D'.
               88  INV-BACKORDER    VALUE 'B'.

       01  WS-CALCULATED-FIELDS.
           05  WS-LINE-AMOUNT      PIC 9(9)V99.
           05  WS-DISCOUNT-AMOUNT  PIC 9(7)V99.
           05  WS-SUBTOTAL         PIC 9(9)V99.
           05  WS-TAX-AMOUNT       PIC 9(7)V99.
           05  WS-ORDER-TOTAL      PIC 9(9)V99.
           05  WS-NEW-BALANCE      PIC S9(9)V99.

       01  WS-ERROR-CODE           PIC X(4).
           88  NO-ERROR            VALUE '0000'.
           88  ERR-INVALID-ACCT    VALUE 'E001'.
           88  ERR-ACCT-CLOSED     VALUE 'E002'.
           88  ERR-ACCT-SUSPENDED  VALUE 'E003'.
           88  ERR-CREDIT-EXCEED   VALUE 'E004'.
           88  ERR-PAST-DUE        VALUE 'E005'.
           88  ERR-INVALID-PROD    VALUE 'E006'.
           88  ERR-NO-STOCK        VALUE 'E007'.
           88  ERR-QTY-RANGE       VALUE 'E008'.
           88  ERR-DISC-LIMIT      VALUE 'E009'.
           88  ERR-DUE-DATE        VALUE 'E010'.
           88  ERR-INVALID-TYPE    VALUE 'E011'.
           88  ERR-DISCONTINUED    VALUE 'E012'.

       01  WS-VALIDATION-FLAG      PIC X(1) VALUE 'Y'.
           88  VALIDATION-PASSED   VALUE 'Y'.
           88  VALIDATION-FAILED   VALUE 'N'.

       01  WS-MAX-DISCOUNT-STANDARD PIC 9(2)V99 VALUE 15.00.
       01  WS-MAX-DISCOUNT-GOLD     PIC 9(2)V99 VALUE 25.00.
       01  WS-MAX-DISCOUNT-PLATINUM PIC 9(2)V99 VALUE 35.00.
       01  WS-PAST-DUE-THRESHOLD   PIC 9(7)V99 VALUE 500.00.
       01  WS-MIN-DUE-DATE-DAYS    PIC 9(2) VALUE 3.
       01  WS-RUSH-MIN-TIER        PIC X(1) VALUE 'G'.

       PROCEDURE DIVISION.

       0000-MAIN-PROCESS.
           PERFORM 1000-VALIDATE-ORDER
           IF VALIDATION-PASSED
               PERFORM 2000-CALCULATE-PRICING
               PERFORM 3000-CHECK-CREDIT
               IF VALIDATION-PASSED
                   PERFORM 4000-RESERVE-INVENTORY
                   IF VALIDATION-PASSED
                       PERFORM 5000-SUBMIT-ORDER
                   END-IF
               END-IF
           END-IF
           PERFORM 9000-RETURN-RESULT
           STOP RUN.

       1000-VALIDATE-ORDER.
      *--- Validate order type ---
           IF NOT VALID-ORDER-TYPE
               SET ERR-INVALID-TYPE TO TRUE
               SET VALIDATION-FAILED TO TRUE
               GO TO 1000-EXIT
           END-IF

      *--- Validate account exists and is eligible ---
           READ ACCOUNT-FILE INTO WS-ACCOUNT-RECORD
               KEY IS WS-ACCOUNT-ID
               INVALID KEY
                   SET ERR-INVALID-ACCT TO TRUE
                   SET VALIDATION-FAILED TO TRUE
                   GO TO 1000-EXIT
           END-READ

           IF ACCT-CLOSED
               SET ERR-ACCT-CLOSED TO TRUE
               SET VALIDATION-FAILED TO TRUE
               GO TO 1000-EXIT
           END-IF

      *--- Suspended accounts: only allow disconnects ---
      *--- Added 2005-11-20 per ticket #4472 ---
           IF ACCT-SUSPENDED
               IF WS-ORDER-TYPE NOT = 'DIS'
                   SET ERR-ACCT-SUSPENDED TO TRUE
                   SET VALIDATION-FAILED TO TRUE
                   GO TO 1000-EXIT
               END-IF
           END-IF

      *--- Check past due balance ---
           IF ACCT-PAST-DUE-AMT > WS-PAST-DUE-THRESHOLD
               IF NOT TIER-PLATINUM
                   SET ERR-PAST-DUE TO TRUE
                   SET VALIDATION-FAILED TO TRUE
                   GO TO 1000-EXIT
               END-IF
           END-IF

      *--- Validate product for NEW and MOD orders ---
           IF WS-ORDER-TYPE = 'NEW' OR WS-ORDER-TYPE = 'MOD'
               READ INVENTORY-FILE INTO WS-INVENTORY-RECORD
                   KEY IS WS-PRODUCT-ID
                   INVALID KEY
                       SET ERR-INVALID-PROD TO TRUE
                       SET VALIDATION-FAILED TO TRUE
                       GO TO 1000-EXIT
               END-READ

               IF INV-DISCONTINUED
                   SET ERR-DISCONTINUED TO TRUE
                   SET VALIDATION-FAILED TO TRUE
                   GO TO 1000-EXIT
               END-IF

               IF WS-QUANTITY < INV-MIN-ORDER-QTY OR
                  WS-QUANTITY > INV-MAX-ORDER-QTY
                   SET ERR-QTY-RANGE TO TRUE
                   SET VALIDATION-FAILED TO TRUE
                   GO TO 1000-EXIT
               END-IF

               IF INV-AVAILABLE
                   IF WS-QUANTITY >
                      (INV-AVAILABLE-QTY - INV-RESERVED-QTY)
                       SET ERR-NO-STOCK TO TRUE
                       SET VALIDATION-FAILED TO TRUE
                       GO TO 1000-EXIT
                   END-IF
               ELSE
                   SET ERR-NO-STOCK TO TRUE
                   SET VALIDATION-FAILED TO TRUE
                   GO TO 1000-EXIT
               END-IF
           END-IF

      *--- Validate discount limits by tier ---
           EVALUATE TRUE
               WHEN TIER-PLATINUM
                   IF WS-DISCOUNT-PCT > WS-MAX-DISCOUNT-PLATINUM
                       SET ERR-DISC-LIMIT TO TRUE
                       SET VALIDATION-FAILED TO TRUE
                       GO TO 1000-EXIT
                   END-IF
               WHEN TIER-GOLD
                   IF WS-DISCOUNT-PCT > WS-MAX-DISCOUNT-GOLD
                       SET ERR-DISC-LIMIT TO TRUE
                       SET VALIDATION-FAILED TO TRUE
                       GO TO 1000-EXIT
                   END-IF
               WHEN OTHER
                   IF WS-DISCOUNT-PCT > WS-MAX-DISCOUNT-STANDARD
                       SET ERR-DISC-LIMIT TO TRUE
                       SET VALIDATION-FAILED TO TRUE
                       GO TO 1000-EXIT
                   END-IF
           END-EVALUATE

      *--- Validate priority: rush orders only for Gold+ ---
           IF WS-PRIORITY = 'S'
               IF NOT (TIER-PLATINUM OR TIER-GOLD)
                   MOVE 'N' TO WS-PRIORITY
               END-IF
           END-IF

      *--- Validate due date (minimum 3 business days out) ---
      *--- Implicit: no validation on disconnect orders ---
           IF WS-ORDER-TYPE NOT = 'DIS'
               PERFORM 1500-CHECK-DUE-DATE
           END-IF

           .
       1000-EXIT.
           EXIT.

       1500-CHECK-DUE-DATE.
      *--- Calculate business days between order date and due date
      *--- Simplified: assumes no holidays, Mon-Fri only
           IF WS-REQUESTED-DUE < WS-ORDER-DATE
               SET ERR-DUE-DATE TO TRUE
               SET VALIDATION-FAILED TO TRUE
           ELSE
               IF WS-REQUESTED-DUE = WS-ORDER-DATE
                   IF NOT (WS-PRIORITY = 'S' AND TIER-PLATINUM)
                       SET ERR-DUE-DATE TO TRUE
                       SET VALIDATION-FAILED TO TRUE
                   END-IF
               END-IF
           END-IF
           .

       2000-CALCULATE-PRICING.
      *--- Skip pricing for disconnect orders ---
           IF WS-ORDER-TYPE = 'DIS'
               MOVE ZEROS TO WS-ORDER-TOTAL
               GO TO 2000-EXIT
           END-IF

           COMPUTE WS-LINE-AMOUNT =
               WS-QUANTITY * WS-UNIT-PRICE

           COMPUTE WS-DISCOUNT-AMOUNT =
               WS-LINE-AMOUNT * (WS-DISCOUNT-PCT / 100)

           COMPUTE WS-SUBTOTAL =
               WS-LINE-AMOUNT - WS-DISCOUNT-AMOUNT

      *--- Tax exempt for government accounts (region = GOVT) ---
           IF ACCT-REGION = 'GOVT'
               MOVE ZEROS TO WS-TAX-AMOUNT
           ELSE
               COMPUTE WS-TAX-AMOUNT =
                   WS-SUBTOTAL * WS-TAX-RATE
           END-IF

           COMPUTE WS-ORDER-TOTAL =
               WS-SUBTOTAL + WS-TAX-AMOUNT

           .
       2000-EXIT.
           EXIT.

       3000-CHECK-CREDIT.
      *--- Skip credit check for disconnect orders ---
           IF WS-ORDER-TYPE = 'DIS'
               GO TO 3000-EXIT
           END-IF

           COMPUTE WS-NEW-BALANCE =
               ACCT-CURRENT-BAL + WS-ORDER-TOTAL

           IF WS-NEW-BALANCE > ACCT-CREDIT-LIMIT
      *--- Platinum accounts get 10% credit overage allowance ---
               IF TIER-PLATINUM
                   IF WS-NEW-BALANCE >
                      (ACCT-CREDIT-LIMIT * 1.10)
                       SET ERR-CREDIT-EXCEED TO TRUE
                       SET VALIDATION-FAILED TO TRUE
                   END-IF
               ELSE
                   SET ERR-CREDIT-EXCEED TO TRUE
                   SET VALIDATION-FAILED TO TRUE
               END-IF
           END-IF
           .
       3000-EXIT.
           EXIT.

       4000-RESERVE-INVENTORY.
      *--- No inventory action for disconnect orders ---
           IF WS-ORDER-TYPE = 'DIS'
               GO TO 4000-EXIT
           END-IF

           ADD WS-QUANTITY TO INV-RESERVED-QTY
           REWRITE INVENTORY-FILE FROM WS-INVENTORY-RECORD
           .
       4000-EXIT.
           EXIT.

       5000-SUBMIT-ORDER.
           MOVE '0000' TO WS-ERROR-CODE
           WRITE ORDER-FILE FROM WS-ORDER-RECORD
           .

       9000-RETURN-RESULT.
           IF VALIDATION-PASSED
               DISPLAY 'ORDER SUBMITTED: ' WS-ORDER-ID
                       ' TOTAL: ' WS-ORDER-TOTAL
           ELSE
               DISPLAY 'ORDER REJECTED: ' WS-ORDER-ID
                       ' ERROR: ' WS-ERROR-CODE
           END-IF
           .
