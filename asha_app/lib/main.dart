import 'package:flutter/material.dart';

import 'api.dart';
import 'db.dart';
import 'screens/home_screen.dart';

void main() {
  runApp(const AshaApp());
}

class AshaApp extends StatelessWidget {
  const AshaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Genomind ASHA',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF0F62FE)),
        useMaterial3: true,
      ),
      home: const Gate(),
    );
  }
}

/// Shows login until a token exists, then the home screen.
class Gate extends StatefulWidget {
  const Gate({super.key});

  @override
  State<Gate> createState() => _GateState();
}

class _GateState extends State<Gate> {
  bool? loggedIn;
  String? username;

  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    final t = await Api.token();
    final u = await Api.savedUser();
    setState(() {
      loggedIn = t != null;
      username = u;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (loggedIn == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return loggedIn!
        ? HomeScreen(username: username ?? 'asha')
        : const LoginScreen();
  }
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _user = TextEditingController(text: 'asha1');
  final _pass = TextEditingController(text: 'changeme');
  String? err;
  bool busy = false;

  Future<void> _go() async {
    setState(() { busy = true; err = null; });
    try {
      final ok = await Api.login(_user.text.trim(), _pass.text);
      if (!ok) {
        setState(() { err = 'गलत उपयोगकर्ता नाम या पासवर्ड / Wrong username or password'; busy = false; });
        return;
      }
      try { await Api.cacheQuestionnaire(); } catch (_) {/* offline: cached copy stays */}
      if (mounted) Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => HomeScreen(username: _user.text.trim())));
    } catch (e) {
      setState(() { err = 'सर्वर से संपर्क नहीं / Cannot reach server'; busy = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(28),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 380),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(22),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  const Icon(Icons.health_and_safety, size: 44, color: Color(0xFF0F62FE)),
                  const SizedBox(height: 8),
                  const Text('Genomind ASHA',
                      style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                  const Text('दुर्लभ रोग जांच सहायक', style: TextStyle(color: Colors.black54)),
                  const SizedBox(height: 18),
                  if (err != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(err!, style: const TextStyle(color: Colors.red)),
                    ),
                  TextField(controller: _user,
                      decoration: const InputDecoration(labelText: 'उपयोगकर्ता नाम / Username')),
                  const SizedBox(height: 10),
                  TextField(controller: _pass, obscureText: true,
                      decoration: const InputDecoration(labelText: 'पासवर्ड / Password')),
                  const SizedBox(height: 18),
                  SizedBox(width: double.infinity, child: FilledButton(
                    onPressed: busy ? null : _go,
                    child: Text(busy ? '...' : 'लॉग इन / Sign in'),
                  )),
                ]),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
