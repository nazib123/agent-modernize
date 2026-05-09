       IDENTIFICATION DIVISION.
       PROGRAM-ID. BANK-TRANSACTION-PROCESSOR.
      *================================================================*
      * Bank Transaction Processing System                              *
      * Synthetic scenario for cross-domain generalization testing.      *
      * Processes deposits, withdrawals, transfers, and balance queries *
      * with multi-tier account validation and fraud detection.         *
      *================================================================*

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT TRANS-FILE ASSIGN TO 'TRANSIN'
               ORGANIZATION IS SEQUENTIAL.
           SELECT ACCOUNT-FILE ASSIGN TO 'ACCTMST'
               ORGANIZATION IS INDEXED
               ACCESS MODE IS DYNAMIC
               RECORD KEY IS ACCT-KEY.
           SELECT AUDIT-FILE ASSIGN TO 'AUDITLOG'
               ORGANIZATION IS SEQUENTIAL.

       DATA DIVISION.
       FILE SECTION.
       FD TRANS-FILE.
       01  TRANS-RECORD.
           05 TR-TRANS-ID          PIC X(12).
           05 TR-ACCOUNT-NO        PIC X(10).
           05 TR-TRANS-TYPE        PIC X(3).
              88 TR-DEPOSIT        VALUE 'DEP'.
              88 TR-WITHDRAWAL     VALUE 'WDR'.
              88 TR-TRANSFER       VALUE 'TRF'.
              88 TR-BALANCE-INQ    VALUE 'BAL'.
           05 TR-AMOUNT            PIC S9(9)V99.
           05 TR-TARGET-ACCT       PIC X(10).
           05 TR-TIMESTAMP         PIC X(26).

       FD ACCOUNT-FILE.
       01  ACCOUNT-RECORD.
           05 ACCT-KEY             PIC X(10).
           05 ACCT-NAME            PIC X(30).
           05 ACCT-TYPE            PIC X(1).
              88 ACCT-CHECKING     VALUE 'C'.
              88 ACCT-SAVINGS      VALUE 'S'.
              88 ACCT-BUSINESS     VALUE 'B'.
           05 ACCT-STATUS          PIC X(1).
              88 ACCT-ACTIVE       VALUE 'A'.
              88 ACCT-FROZEN       VALUE 'F'.
              88 ACCT-CLOSED       VALUE 'X'.
              88 ACCT-DORMANT      VALUE 'D'.
           05 ACCT-BALANCE         PIC S9(9)V99.
           05 ACCT-DAILY-WDR-TOTAL PIC S9(9)V99.
           05 ACCT-DAILY-WDR-COUNT PIC 9(3).
           05 ACCT-OVERDRAFT-LIMIT PIC S9(7)V99.
           05 ACCT-TIER            PIC X(1).
              88 TIER-STANDARD     VALUE 'S'.
              88 TIER-PREMIUM      VALUE 'P'.
              88 TIER-VIP          VALUE 'V'.
           05 ACCT-LAST-ACTIVITY   PIC X(10).

       FD AUDIT-FILE.
       01  AUDIT-RECORD            PIC X(200).

       WORKING-STORAGE SECTION.
       01  WS-CONSTANTS.
           05 WS-MAX-WDR-STANDARD  PIC S9(7)V99  VALUE 5000.00.
           05 WS-MAX-WDR-PREMIUM   PIC S9(7)V99  VALUE 25000.00.
           05 WS-MAX-WDR-VIP       PIC S9(7)V99  VALUE 100000.00.
           05 WS-MAX-DAILY-WDR-STD PIC 9(3)       VALUE 3.
           05 WS-MAX-DAILY-WDR-PRM PIC 9(3)       VALUE 10.
           05 WS-MAX-DAILY-WDR-VIP PIC 9(3)       VALUE 999.
           05 WS-FRAUD-THRESHOLD   PIC S9(7)V99  VALUE 10000.00.
           05 WS-DORMANT-MONTHS    PIC 9(2)       VALUE 12.
           05 WS-MIN-BALANCE-SAV   PIC S9(7)V99  VALUE 100.00.
           05 WS-OVERDRAFT-FEE     PIC S9(5)V99  VALUE 35.00.
           05 WS-TRANSFER-FEE-STD  PIC S9(5)V99  VALUE 25.00.
           05 WS-TRANSFER-FEE-PRM  PIC S9(5)V99  VALUE 0.00.

       01  WS-PROCESSING.
           05 WS-RESULT-CODE       PIC X(4).
           05 WS-RESULT-MSG        PIC X(80).
           05 WS-NEW-BALANCE       PIC S9(9)V99.
           05 WS-EFFECTIVE-AMT     PIC S9(9)V99.
           05 WS-TRANSFER-FEE      PIC S9(5)V99.
           05 WS-FRAUD-FLAG        PIC X(1) VALUE 'N'.
              88 FRAUD-DETECTED    VALUE 'Y'.
           05 WS-OVERDRAFT-USED    PIC X(1) VALUE 'N'.
              88 OVERDRAFT-APPLIED VALUE 'Y'.

       01  WS-TARGET-ACCOUNT.
           05 TGT-KEY              PIC X(10).
           05 TGT-STATUS           PIC X(1).
           05 TGT-BALANCE          PIC S9(9)V99.
           05 TGT-TYPE             PIC X(1).

       PROCEDURE DIVISION.
       MAIN-PROCESS.
           OPEN INPUT TRANS-FILE
           OPEN I-O   ACCOUNT-FILE
           OPEN OUTPUT AUDIT-FILE

           READ TRANS-FILE
               AT END GO TO CLOSE-FILES
           END-READ

           PERFORM PROCESS-TRANSACTION
           PERFORM CLOSE-FILES
           STOP RUN.

       PROCESS-TRANSACTION.
      *    ---- Step 1: Validate transaction type ----
           IF NOT (TR-DEPOSIT OR TR-WITHDRAWAL
                   OR TR-TRANSFER OR TR-BALANCE-INQ)
               MOVE 'E001' TO WS-RESULT-CODE
               MOVE 'Invalid transaction type' TO WS-RESULT-MSG
               PERFORM WRITE-AUDIT
               GO TO PROCESS-EXIT
           END-IF

      *    ---- Step 2: Look up source account ----
           MOVE TR-ACCOUNT-NO TO ACCT-KEY
           READ ACCOUNT-FILE
               INVALID KEY
                   MOVE 'E002' TO WS-RESULT-CODE
                   MOVE 'Account not found' TO WS-RESULT-MSG
                   PERFORM WRITE-AUDIT
                   GO TO PROCESS-EXIT
           END-READ

      *    ---- Step 3: Account status checks ----
           IF ACCT-CLOSED
               MOVE 'E003' TO WS-RESULT-CODE
               MOVE 'Account is closed' TO WS-RESULT-MSG
               PERFORM WRITE-AUDIT
               GO TO PROCESS-EXIT
           END-IF

           IF ACCT-FROZEN
               IF NOT TR-BALANCE-INQ
                   MOVE 'E004' TO WS-RESULT-CODE
                   MOVE 'Account frozen - only inquiries allowed'
                       TO WS-RESULT-MSG
                   PERFORM WRITE-AUDIT
                   GO TO PROCESS-EXIT
               END-IF
           END-IF

      *    ---- Step 3a: Dormant account reactivation ----
           IF ACCT-DORMANT
               IF TR-DEPOSIT
                   MOVE 'A' TO ACCT-STATUS
                   MOVE 'Dormant account reactivated via deposit'
                       TO WS-RESULT-MSG
               ELSE
                   MOVE 'E005' TO WS-RESULT-CODE
                   MOVE 'Dormant account - deposit required first'
                       TO WS-RESULT-MSG
                   PERFORM WRITE-AUDIT
                   GO TO PROCESS-EXIT
               END-IF
           END-IF

      *    ---- Step 4: Amount validation ----
           IF NOT TR-BALANCE-INQ
               IF TR-AMOUNT <= 0
                   MOVE 'E006' TO WS-RESULT-CODE
                   MOVE 'Amount must be positive' TO WS-RESULT-MSG
                   PERFORM WRITE-AUDIT
                   GO TO PROCESS-EXIT
               END-IF
           END-IF

      *    ---- Step 5: Fraud detection ----
           IF TR-WITHDRAWAL OR TR-TRANSFER
               IF TR-AMOUNT > WS-FRAUD-THRESHOLD
                   MOVE 'Y' TO WS-FRAUD-FLAG
               END-IF
           END-IF

      *    ---- Step 6: Process by transaction type ----
           EVALUATE TRUE
               WHEN TR-DEPOSIT
                   PERFORM PROCESS-DEPOSIT
               WHEN TR-WITHDRAWAL
                   PERFORM PROCESS-WITHDRAWAL
               WHEN TR-TRANSFER
                   PERFORM PROCESS-TRANSFER
               WHEN TR-BALANCE-INQ
                   PERFORM PROCESS-INQUIRY
           END-EVALUATE.

       PROCESS-EXIT.
           EXIT.

       PROCESS-DEPOSIT.
           ADD TR-AMOUNT TO ACCT-BALANCE
           MOVE ACCT-BALANCE TO WS-NEW-BALANCE
           REWRITE ACCOUNT-RECORD
           MOVE '0000' TO WS-RESULT-CODE
           STRING 'Deposit successful. New balance: '
                  ACCT-BALANCE DELIMITED SIZE
                  INTO WS-RESULT-MSG
           PERFORM WRITE-AUDIT.

       PROCESS-WITHDRAWAL.
      *    Check per-transaction withdrawal limit by tier
           EVALUATE TRUE
               WHEN TIER-VIP
                   IF TR-AMOUNT > WS-MAX-WDR-VIP
                       MOVE 'E007' TO WS-RESULT-CODE
                       MOVE 'Exceeds VIP withdrawal limit'
                           TO WS-RESULT-MSG
                       PERFORM WRITE-AUDIT
                       GO TO PROCESS-EXIT
                   END-IF
               WHEN TIER-PREMIUM
                   IF TR-AMOUNT > WS-MAX-WDR-PREMIUM
                       MOVE 'E008' TO WS-RESULT-CODE
                       MOVE 'Exceeds Premium withdrawal limit'
                           TO WS-RESULT-MSG
                       PERFORM WRITE-AUDIT
                       GO TO PROCESS-EXIT
                   END-IF
               WHEN OTHER
                   IF TR-AMOUNT > WS-MAX-WDR-STANDARD
                       MOVE 'E009' TO WS-RESULT-CODE
                       MOVE 'Exceeds Standard withdrawal limit'
                           TO WS-RESULT-MSG
                       PERFORM WRITE-AUDIT
                       GO TO PROCESS-EXIT
                   END-IF
           END-EVALUATE

      *    Check daily withdrawal count limit
           EVALUATE TRUE
               WHEN TIER-VIP
                   CONTINUE
               WHEN TIER-PREMIUM
                   IF ACCT-DAILY-WDR-COUNT >= WS-MAX-DAILY-WDR-PRM
                       MOVE 'E010' TO WS-RESULT-CODE
                       MOVE 'Daily withdrawal count exceeded'
                           TO WS-RESULT-MSG
                       PERFORM WRITE-AUDIT
                       GO TO PROCESS-EXIT
                   END-IF
               WHEN OTHER
                   IF ACCT-DAILY-WDR-COUNT >= WS-MAX-DAILY-WDR-STD
                       MOVE 'E010' TO WS-RESULT-CODE
                       MOVE 'Daily withdrawal count exceeded'
                           TO WS-RESULT-MSG
                       PERFORM WRITE-AUDIT
                       GO TO PROCESS-EXIT
                   END-IF
           END-EVALUATE

      *    Compute new balance with overdraft logic
           SUBTRACT TR-AMOUNT FROM ACCT-BALANCE
               GIVING WS-NEW-BALANCE

           IF WS-NEW-BALANCE < 0
               IF ACCT-CHECKING
                   IF FUNCTION ABS(WS-NEW-BALANCE) <=
                      ACCT-OVERDRAFT-LIMIT
                       MOVE 'Y' TO WS-OVERDRAFT-USED
                       SUBTRACT WS-OVERDRAFT-FEE FROM WS-NEW-BALANCE
                   ELSE
                       MOVE 'E011' TO WS-RESULT-CODE
                       MOVE 'Insufficient funds - overdraft exceeded'
                           TO WS-RESULT-MSG
                       PERFORM WRITE-AUDIT
                       GO TO PROCESS-EXIT
                   END-IF
               ELSE
                   MOVE 'E012' TO WS-RESULT-CODE
                   MOVE 'Insufficient funds - no overdraft'
                       TO WS-RESULT-MSG
                   PERFORM WRITE-AUDIT
                   GO TO PROCESS-EXIT
               END-IF
           END-IF

      *    Savings minimum balance check
           IF ACCT-SAVINGS
               IF WS-NEW-BALANCE < WS-MIN-BALANCE-SAV
                   MOVE 'E013' TO WS-RESULT-CODE
                   MOVE 'Below minimum savings balance'
                       TO WS-RESULT-MSG
                   PERFORM WRITE-AUDIT
                   GO TO PROCESS-EXIT
               END-IF
           END-IF

           MOVE WS-NEW-BALANCE TO ACCT-BALANCE
           ADD 1 TO ACCT-DAILY-WDR-COUNT
           ADD TR-AMOUNT TO ACCT-DAILY-WDR-TOTAL
           REWRITE ACCOUNT-RECORD

           IF FRAUD-DETECTED
               MOVE 'W001' TO WS-RESULT-CODE
               MOVE 'Withdrawal processed - FLAGGED for review'
                   TO WS-RESULT-MSG
           ELSE
               MOVE '0000' TO WS-RESULT-CODE
               MOVE 'Withdrawal successful' TO WS-RESULT-MSG
           END-IF
           PERFORM WRITE-AUDIT.

       PROCESS-TRANSFER.
      *    Validate target account
           MOVE TR-TARGET-ACCT TO TGT-KEY
           MOVE TR-TARGET-ACCT TO ACCT-KEY
           READ ACCOUNT-FILE
               INVALID KEY
                   MOVE 'E014' TO WS-RESULT-CODE
                   MOVE 'Target account not found'
                       TO WS-RESULT-MSG
                   PERFORM WRITE-AUDIT
                   GO TO PROCESS-EXIT
           END-READ

           MOVE ACCT-STATUS TO TGT-STATUS
           MOVE ACCT-BALANCE TO TGT-BALANCE
           MOVE ACCT-TYPE    TO TGT-TYPE

      *    Target cannot be closed
           IF TGT-STATUS = 'X'
               MOVE 'E015' TO WS-RESULT-CODE
               MOVE 'Target account is closed' TO WS-RESULT-MSG
               PERFORM WRITE-AUDIT
               GO TO PROCESS-EXIT
           END-IF

      *    Reload source account
           MOVE TR-ACCOUNT-NO TO ACCT-KEY
           READ ACCOUNT-FILE
               INVALID KEY
                   MOVE 'E002' TO WS-RESULT-CODE
                   MOVE 'Source account read error' TO WS-RESULT-MSG
                   PERFORM WRITE-AUDIT
                   GO TO PROCESS-EXIT
           END-READ

      *    Calculate transfer fee based on tier
           IF TIER-PREMIUM OR TIER-VIP
               MOVE 0 TO WS-TRANSFER-FEE
           ELSE
               MOVE WS-TRANSFER-FEE-STD TO WS-TRANSFER-FEE
           END-IF

      *    Calculate effective amount
           ADD TR-AMOUNT WS-TRANSFER-FEE GIVING WS-EFFECTIVE-AMT

      *    Check source has enough funds
           IF WS-EFFECTIVE-AMT > ACCT-BALANCE
               MOVE 'E016' TO WS-RESULT-CODE
               MOVE 'Insufficient funds for transfer + fee'
                   TO WS-RESULT-MSG
               PERFORM WRITE-AUDIT
               GO TO PROCESS-EXIT
           END-IF

      *    Debit source
           SUBTRACT WS-EFFECTIVE-AMT FROM ACCT-BALANCE
           REWRITE ACCOUNT-RECORD

      *    Credit target
           MOVE TR-TARGET-ACCT TO ACCT-KEY
           READ ACCOUNT-FILE
               INVALID KEY
                   MOVE 'E014' TO WS-RESULT-CODE
                   GO TO PROCESS-EXIT
           END-READ
           ADD TR-AMOUNT TO ACCT-BALANCE
           REWRITE ACCOUNT-RECORD

           IF FRAUD-DETECTED
               MOVE 'W002' TO WS-RESULT-CODE
               MOVE 'Transfer processed - FLAGGED for review'
                   TO WS-RESULT-MSG
           ELSE
               MOVE '0000' TO WS-RESULT-CODE
               MOVE 'Transfer successful' TO WS-RESULT-MSG
           END-IF
           PERFORM WRITE-AUDIT.

       PROCESS-INQUIRY.
           MOVE '0000' TO WS-RESULT-CODE
           MOVE ACCT-BALANCE TO WS-NEW-BALANCE
           STRING 'Balance inquiry: ' ACCT-BALANCE
                  DELIMITED SIZE INTO WS-RESULT-MSG
           PERFORM WRITE-AUDIT.

       WRITE-AUDIT.
           STRING TR-TRANS-ID '|' TR-ACCOUNT-NO '|' TR-TRANS-TYPE '|'
                  TR-AMOUNT '|' WS-RESULT-CODE '|' WS-FRAUD-FLAG '|'
                  WS-RESULT-MSG
                  DELIMITED SIZE INTO AUDIT-RECORD
           WRITE AUDIT-RECORD.

       CLOSE-FILES.
           CLOSE TRANS-FILE ACCOUNT-FILE AUDIT-FILE.
