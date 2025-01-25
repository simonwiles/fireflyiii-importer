import csv
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Iterator

import requests

from transaction import Config, Transaction


class FireflyImporter:
    def __init__(self, base_url: str, access_token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        self.account_map = self._get_account_map()

        self.transactions_created = 0
        self.transactions_skipped = 0
        self.transfers_matched = 0

    def _get_account_map(self) -> Dict[str, str]:
        """Fetch all accounts and create a name -> id mapping"""
        response = self.session.get(f"{self.base_url}/api/v1/accounts")
        response.raise_for_status()
        accounts = response.json()["data"]
        return {account["attributes"]["name"]: account["id"] for account in accounts}

    def _generate_external_id(
        self, transaction: Transaction, additional_uid_value: str | None
    ) -> str:
        """Generate a stable external ID for deduplication"""
        key = f"{transaction.date.isoformat()}-{transaction.amount}-{transaction.account}-{transaction.description}"
        if additional_uid_value:
            key += f"-{additional_uid_value}"
        return hashlib.sha256(key.encode()).hexdigest()

    def import_from_csv(self, csv_file: str, csv_config: Config):
        """
        Import transactions from CSV file

        Args:
            csv_files: Dict mapping account names to CSV file paths
            date_format: Format string for parsing dates in CSVs
            csv_config: Dict with column names for date, description, and amount
        """
        transactions = self._parse_csv_transactions(csv_file, csv_config)

        for transaction in transactions:
            if self._find_transaction_by_external_id(transaction.external_id):
                logging.info(f"Transaction {transaction.external_id} already exists")
                self.transactions_skipped += 1
                continue

            if transaction.type == "transfer":
                transfer = self._find_matching_transfer(
                    transaction, csv_config.date_window_days
                )
                if transfer:
                    logging.info(f"Matching transfer found: {transfer['id']}")
                    self.transfers_matched += 1
                    continue

            self._create_transaction(transaction)

        print(f"Created {self.transactions_created} transactions")
        print(f"Skipped {self.transactions_skipped} transactions")
        print(f"Transfers matched: {self.transfers_matched}")

    def _parse_csv_transactions(
        self, filepath: str, config: Config
    ) -> Iterator[Transaction]:
        """Read transactions from a CSV file"""

        account = config.account

        date_format = config.date_format
        date_column = config.date_column

        description_column = config.description_column
        amount_column = config.amount_column
        credit_column = config.credit_column
        debit_column = config.debit_column

        if amount_column is None:
            if credit_column is None or debit_column is None:
                raise ValueError(
                    "If amount_column is not provided, both credit_column and debit_column must be provided"
                )

        with open(filepath, "r", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for i, row in reversed(list(enumerate(reader))):
                row = {
                    k: v.strip() if isinstance(v, str) else v for k, v in row.items()
                }

                if amount_column is not None:
                    amount = float(row[amount_column])
                    if config.invert_amount:
                        amount = 0 - amount
                elif row[credit_column] == "":
                    amount = 0 - float(row[debit_column])
                else:
                    amount = float(row[credit_column])

                description = row[description_column]
                if row.get("Check", None):
                    description += row["Check"]

                transaction = Transaction(
                    date=datetime.strptime(row[date_column], date_format),
                    description=description,
                    amount=amount,
                    account=account,
                    external_id="",
                )

                transaction.type = "withdrawal" if transaction.amount < 0 else "deposit"

                additional_uid_value = None
                if config.additional_uid_column:
                    if config.additional_uid_column == "idx":
                        additional_uid_value = str(i)
                    else:
                        additional_uid_value = row[config.additional_uid_column]

                transaction.external_id = self._generate_external_id(
                    transaction, additional_uid_value
                )

                if destination := config.transfers_out.get(row["Description"]):
                    transaction.type = "transfer"
                    transaction.source_name = account
                    transaction.destination_name = destination

                if source := config.transfers_in.get(row["Description"]):
                    transaction.type = "transfer"
                    transaction.source_name = source
                    transaction.destination_name = account

                yield transaction

    def _create_transaction(self, transaction: Transaction):
        """Create a regular transaction"""

        data = {
            "transactions": [
                {
                    "type": transaction.type,
                    "date": transaction.date.strftime("%Y-%m-%d"),
                    "amount": str(abs(transaction.amount)),
                    "description": transaction.description,
                    "external_id": transaction.external_id,
                    "source_name": transaction.source_name or transaction.account,
                    "destination_name": transaction.destination_name
                    or ("Cash" if transaction.amount < 0 else transaction.account),
                }
            ],
        }

        response = self.session.post(f"{self.base_url}/api/v1/transactions", json=data)
        logging.info(
            "Created %s: %f - %s",
            transaction.type,
            transaction.amount,
            transaction.description,
        )
        self.transactions_created += 1
        response.raise_for_status()

    def _find_transaction_by_external_id(self, external_id):
        """Search for existing transaction with this external_id."""
        response = self.session.get(
            f"{self.base_url}/api/v1/search/transactions",
            params={"query": f"external_id_is:{external_id}"},
        )
        results = response.json().get("data", [])
        return results[0] if results else None

    def _find_matching_transfer(
        self, transaction: Transaction, date_window_days: int | None
    ):
        """Search for existing transaction with this external_id."""

        query_params = {
            "type": "transfer",
            "amount": str(abs(transaction.amount)),
            "source_account_is": f'"{transaction.source_name or transaction.account}"',
            "destination_account_is": f'"{transaction.destination_name}"',
            # don't match if the description is the same;
            #  sometimes we may have two transactions in the same direction between
            #  the same two accounts for the same amount on the same day;
            #  this should prevent the second one being skipped as a duplicate
            "-description_is": f'"{transaction.description}"',
        }

        if date_window_days is None:
            query_params["date_on"] = transaction.date.strftime("%Y-%m-%d")
        else:
            query_params["date_after"] = (
                transaction.date - timedelta(days=date_window_days)
            ).strftime("%Y-%m-%d")
            query_params["date_before"] = (
                transaction.date + timedelta(days=date_window_days)
            ).strftime("%Y-%m-%d")

        query = self._dict_to_search_query(query_params)

        logging.debug(f"Searching for: {query}")

        response = self.session.get(
            f"{self.base_url}/api/v1/search/transactions",
            params={"query": query},
        )
        results = response.json().get("data", [])
        return results[0] if results else None

    def _dict_to_search_query(self, data):
        """Convert a dictionary of key-value pairs into a Firefly III search query."""
        return " ".join([":".join([k, v]) for k, v in data.items()])
