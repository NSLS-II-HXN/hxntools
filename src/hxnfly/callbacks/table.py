import bluesky.callbacks


class BulkLiveTable(bluesky.callbacks.LiveTable):
    def bulk_events(self, keyed_docs):
        for uid, docs in keyed_docs.items():
            for doc in docs:
                self.event(doc)
