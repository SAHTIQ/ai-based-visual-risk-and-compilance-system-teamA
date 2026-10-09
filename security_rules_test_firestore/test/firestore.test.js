const { initializeTestEnvironment, assertFails, assertSucceeds } = require("@firebase/rules-unit-testing");
const fs = require("fs");
const path = require("path");
const { expect } = require("chai");

const PROJECT_ID = "quanta-security-test";
let testEnv;

before(async () => {
  const rulesPath = path.resolve(__dirname, "../../firestore.rules");
  const rules = fs.readFileSync(rulesPath, "utf8");

  testEnv = await initializeTestEnvironment({
    projectId: PROJECT_ID,
    firestore: { rules }
  });
});

beforeEach(async () => {
  await testEnv.clearFirestore();
});

after(async () => {
  if (testEnv) {
    await testEnv.cleanup();
  }
});

describe("Quanta Digital Twin — Firestore Security Rules", () => {

  describe("1. User Profiles (/users/{userId})", () => {
    it("should allow an authenticated user to read their own profile", async () => {
      const alice = testEnv.authenticatedContext("alice");
      await testEnv.withSecurityRulesDisabled(async (context) => {
        await context.firestore().collection("users").doc("alice").set({
          uid: "alice",
          email: "alice@example.com",
          display_name: "Alice"
        });
      });
      await assertSucceeds(alice.firestore().collection("users").doc("alice").get());
    });

    it("should deny an unauthenticated visitor from reading any user profile", async () => {
      const unauth = testEnv.unauthenticatedContext();
      await assertFails(unauth.firestore().collection("users").doc("alice").get());
    });

    it("should deny an authenticated user from reading another user's profile", async () => {
      const bob = testEnv.authenticatedContext("bob");
      await assertFails(bob.firestore().collection("users").doc("alice").get());
    });

    it("should allow a user to create their own profile with valid fields", async () => {
      const alice = testEnv.authenticatedContext("alice");
      await assertSucceeds(alice.firestore().collection("users").doc("alice").set({
        uid: "alice",
        email: "alice@example.com",
        display_name: "Alice"
      }));
    });
  });

  describe("2. Financial Records (/expenses & /income)", () => {
    it("should allow a user to create an expense for themselves with amount > 0", async () => {
      const alice = testEnv.authenticatedContext("alice");
      await assertSucceeds(alice.firestore().collection("expenses").doc("exp_1").set({
        uid: "alice",
        category: "food",
        amount: 250,
        date: "2026-09-21"
      }));
    });

    it("should reject an expense created with amount <= 0", async () => {
      const alice = testEnv.authenticatedContext("alice");
      await assertFails(alice.firestore().collection("expenses").doc("exp_2").set({
        uid: "alice",
        category: "food",
        amount: -50,
        date: "2026-09-21"
      }));
    });

    it("should deny User B from reading User A's expenses", async () => {
      await testEnv.withSecurityRulesDisabled(async (context) => {
        await context.firestore().collection("expenses").doc("exp_alice").set({
          uid: "alice",
          category: "food",
          amount: 100
        });
      });
      const bob = testEnv.authenticatedContext("bob");
      await assertFails(bob.firestore().collection("expenses").doc("exp_alice").get());
    });

    it("should deny User B from modifying User A's expenses", async () => {
      await testEnv.withSecurityRulesDisabled(async (context) => {
        await context.firestore().collection("expenses").doc("exp_alice").set({
          uid: "alice",
          category: "food",
          amount: 100
        });
      });
      const bob = testEnv.authenticatedContext("bob");
      await assertFails(bob.firestore().collection("expenses").doc("exp_alice").update({
        amount: 500
      }));
    });
  });

  describe("3. Study & Productivity (/study_records)", () => {
    it("should allow a user to log their own study sessions", async () => {
      const alice = testEnv.authenticatedContext("alice");
      await assertSucceeds(alice.firestore().collection("study_records").doc("study_1").set({
        uid: "alice",
        subject: "Linear Algebra",
        duration_minutes: 120,
        date: "2026-09-21"
      }));
    });

    it("should reject study sessions with zero or negative duration", async () => {
      const alice = testEnv.authenticatedContext("alice");
      await assertFails(alice.firestore().collection("study_records").doc("study_2").set({
        uid: "alice",
        subject: "Linear Algebra",
        duration_minutes: 0,
        date: "2026-09-21"
      }));
    });
  });

  describe("4. Audit Trail / Activity History (/activity_history)", () => {
    it("should allow a user to create audit records for their own actions", async () => {
      const alice = testEnv.authenticatedContext("alice");
      await assertSucceeds(alice.firestore().collection("activity_history").doc("act_1").set({
        uid: "alice",
        action: "create",
        entity_type: "expense"
      }));
    });

    it("should deny updates to activity history records (immutable)", async () => {
      await testEnv.withSecurityRulesDisabled(async (context) => {
        await context.firestore().collection("activity_history").doc("act_1").set({
          uid: "alice",
          action: "create",
          entity_type: "expense"
        });
      });
      const alice = testEnv.authenticatedContext("alice");
      await assertFails(alice.firestore().collection("activity_history").doc("act_1").update({
        action: "tampered"
      }));
    });

    it("should deny deletions of activity history records (immutable)", async () => {
      await testEnv.withSecurityRulesDisabled(async (context) => {
        await context.firestore().collection("activity_history").doc("act_1").set({
          uid: "alice",
          action: "create",
          entity_type: "expense"
        });
      });
      const alice = testEnv.authenticatedContext("alice");
      await assertFails(alice.firestore().collection("activity_history").doc("act_1").delete());
    });
  });

  describe("5. Default Deny on Unknown Collections", () => {
    it("should deny read and write on unspecified collections", async () => {
      const alice = testEnv.authenticatedContext("alice");
      await assertFails(alice.firestore().collection("internal_admin_data").doc("doc1").get());
      await assertFails(alice.firestore().collection("internal_admin_data").doc("doc1").set({ data: "leak" }));
    });
  });

});
