"""Couchbase test database creation and destruction."""

from __future__ import annotations

import logging

from django.db.backends.base.creation import BaseDatabaseCreation

logger = logging.getLogger("django.db.backends.couchbase.creation")


class DatabaseCreation(BaseDatabaseCreation):
    def _get_test_db_name(self):
        """Return the test database (bucket) name.

        For Couchbase, we reuse the same bucket. The TEST NAME setting should
        point to the same bucket to avoid creating a new one.
        """
        return self.connection.settings_dict.get("TEST", {}).get(
            "NAME", self.connection.settings_dict["NAME"]
        )

    def _create_test_db(self, verbosity, autoclobber, keepdb=False):
        """For Couchbase, we reuse the existing bucket.

        Collections are created by the migration framework when migrate runs.
        No need to create a separate database.
        """
        test_db_name = self._get_test_db_name()
        if verbosity >= 1:
            logger.info("Using Couchbase bucket '%s' for testing", test_db_name)
        return test_db_name

    def _destroy_test_db(self, test_database_name, verbosity):
        """Clean up test data but don't destroy the bucket."""
        if verbosity >= 1:
            logger.info("Cleaning up test data from bucket '%s'", test_database_name)

    def _clone_test_db(self, suffix, verbosity, keepdb=False):
        """Parallel test DBs not supported."""
        raise NotImplementedError("Couchbase backend does not support parallel test databases.")
