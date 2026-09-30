# Auth Testing Playbook (Emergent Google Auth)

See integration playbook. Test user/session creation:

```
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({ user_id: userId, email: 'test.user.'+Date.now()+'@example.com', name: 'Test Conseiller', picture: '', created_at: new Date() });
db.user_sessions.insertOne({ user_id: userId, session_token: sessionToken, expires_at: new Date(Date.now()+7*24*60*60*1000), created_at: new Date() });
print('Session token: ' + sessionToken);
"
```

Use session_token as Bearer token or cookie `session_token`.
Backend endpoints require auth: /api/auth/me, /api/clients, /api/dashboard/stats, etc.
