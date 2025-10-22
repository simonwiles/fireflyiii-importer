# fireflyiii-importer


```
❭ uv sync
❭ uv run cli.py -v load-csv --config-file /path/to/config-file-for-account.json5 /path/to/transactions-for-account.csv
```


Config file looks like this, and is expected to be needed on a per-account basis (some fields are optional):
```json5
{
  account: "Account Name", // as set in FireflyIII
  date_format: "%m/%d/%Y",
  date_column: "Post Date",
  description_column: "Description",
  credit_column: "Credit",
  debit_column: "Debit",
  additional_uid_column: "Balance",  // affixed to the uid string to ensure otherwise identical transactions aren't incorrectly identified as duplicates
  transfers_out: {
    // maps transaction descriptions to the account they are transfers to
    // you may or may not find this helpful for your purposes
    "Withdrawal Online Transfer to Savings XXXX": "Savings Account",
    "ACH Debit SOME CREDIT CRD  - EPAY": "Credit Card",
  },
  transfers_in: {
    // maps transaction descriptions to the account they are transfers from
    // you may or may not find this helpful for your purposes
    "Deposit Online Transfer from XXXX": "Savings Account",
  },
  invert_amount: false,  // if the sign of the amount should be flipped on import
  date_window_days: 3,  // window in which to search when looking for matching transfers in other accounts 
                        // default: not set (== `None` == match only transactions with the same date)
}

```
