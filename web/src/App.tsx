import { Route, Routes } from 'react-router-dom';

import { AuthGate } from './auth/AuthGate';
import { Health } from './routes/Health';
import { Projects } from './routes/Projects';
import { Questions } from './routes/Questions';

export function App() {
  return (
    <Routes>
      <Route path="/health" element={<Health />} />
      <Route
        path="/*"
        element={
          <AuthGate>
            <Routes>
              <Route path="/" element={<Projects />} />
              <Route path="p/:slug/questions" element={<Questions />} />
            </Routes>
          </AuthGate>
        }
      />
    </Routes>
  );
}
